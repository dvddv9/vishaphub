"""Design: plan the files and collect the gaps.

Two outputs: files and gaps. This step fixes only what the spec alone
decides. Choosing interfaces in detail and checking libraries against
their documentation need an LLM and come later; `library_check` names
the libraries to check, it does not claim they were checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from generator.tools.gaps import Gap, collect, number
from generator.pipeline.intake import Requirement, Source, requirements_from
from generator.tools.spec import Spec
from generator.tools.stride import Threat, stride_table

LIBRARIES = {
    "python/flask": ("flask",),
    "java/spring": ("spring-boot",),
}


@dataclass(frozen=True)
class FilePlan:
    path: str
    role: str                      # code | test | package
    interface: str
    requirements: tuple[str, ...]  # requirement ids this file serves
    measures: tuple[str, ...]      # auth | validation | rate_limit
    library_check: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "role": self.role,
            "interface": self.interface,
            "requirements": list(self.requirements),
            "measures": list(self.measures),
            "library_check": list(self.library_check),
        }


@dataclass(frozen=True)
class DesignResult:
    files: tuple[FilePlan, ...]
    gaps: tuple[Gap, ...]
    threats: tuple[Threat, ...] = ()

    @property
    def critical_gaps(self) -> tuple[Gap, ...]:
        return tuple(g for g in self.gaps if g.severity == "critical")

    def to_dict(self) -> dict:
        return {
            "files": [f.to_dict() for f in self.files],
            "gaps": [g.to_dict() for g in self.gaps],
            "threats": [t.to_dict() for t in self.threats],
        }


def _measures(spec: Spec) -> tuple[str, ...]:
    data = spec.data
    out: list[str] = []
    if data.get("caller") == "signed-in":
        out.append("auth")
    has_rule = any(item.get("rule") for item, _ in spec.items.get("inputs", []))
    if has_rule or "validate-inputs" in (data.get("constraints") or []):
        out.append("validation")
    rule_ids = [item["id"] for f in ("must_never", "should", "may")
                for item, _ in spec.items.get(f, [])]
    if any("rate-limit" in rid for rid in rule_ids):
        out.append("rate_limit")
    return tuple(out)


def _interface(spec: Spec) -> str:
    data = spec.data
    ins = ", ".join(f"{i['name']} ({i['in']})" for i, _ in spec.items.get("inputs", []))
    outs = ", ".join(str(o["status"]) for o, _ in spec.items.get("outputs", []))
    parts = [data.get("kind", "unknown kind")]
    if data.get("route"):
        parts.append(f"route: {data['route']}")
    if ins:
        parts.append(f"inputs: {ins}")
    if outs:
        parts.append(f"outputs: {outs}")
    return "; ".join(parts)


def design(spec: Spec, requirements: tuple[Requirement, ...] | None = None) -> DesignResult:
    reqs = requirements if requirements is not None else requirements_from(spec)
    found = collect(spec)
    data = spec.data
    output = data.get("output")
    target = data.get("target", "")
    files: list[FilePlan] = []

    if output:
        out_path = PurePosixPath(output)
        all_ids = tuple(r.id for r in reqs)
        tested = tuple(r for r in reqs if "test" in r.verify)

        if target.startswith("python/"):
            for parent in reversed(out_path.parents):
                if str(parent) == ".":
                    continue
                files.append(FilePlan(
                    path=str(parent / "__init__.py"), role="package",
                    interface="package marker", requirements=(),
                    measures=(), library_check=(),
                ))

        files.append(FilePlan(
            path=output, role="code", interface=_interface(spec),
            requirements=all_ids, measures=_measures(spec),
            library_check=LIBRARIES.get(target, ()),
        ))

        if target.startswith("python/"):
            names = ", ".join(f"test_{r.id.lower()}" for r in tested)
            files.append(FilePlan(
                path="tests/__init__.py", role="package",
                interface="package marker, so python -m unittest finds the tests",
                requirements=(), measures=(), library_check=(),
            ))
            files.append(FilePlan(
                path=f"tests/test_{out_path.stem}.py", role="test",
                interface=f"tests: {names}" if names else "tests: none",
                requirements=tuple(r.id for r in tested),
                measures=(), library_check=(),
            ))
        elif target:
            found.append((
                "assumption",
                f"tests for target {target} are not planned yet; only the code file is",
                Source("target", spec.key_lines["target"]) if "target" in spec.key_lines else None,
            ))

    return DesignResult(files=tuple(files), gaps=number(found), threats=stride_table(spec, reqs))
