"""Build with an LLM: write the planned files, then check them.

The model gets the requirements, the file plan from Design and the spec
text, and must answer with one JSON object:

    {"files": {"<planned path>": "<file content>", ...}}

The answer goes straight through check_build: missing or extra files,
syntax, ruff when installed, and one test_rN per requirement. Files are
only returned here, never written; writing is Deliver's job.

The spec text is untrusted input. It is passed as data between markers,
and nothing the model says can add a file outside the plan: check_build
reports any such file as an error and Deliver will only write planned
paths.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from generator.pipeline.build import BuildCheck, check_build
from generator.pipeline.design import DesignResult
from generator.pipeline.intake import Requirement
from generator.pipeline.stages import parse_json_response
from generator.pipeline.prompts import build_prompt, load_prompt, wrap_material
from generator.llm import LLMConfig, chat
from generator.tools.spec import Spec

MAX_TOKENS = 8000
BUILD_PROMPT = "03_build"
REPAIR_PROMPT = "03_build_repair"

class GenerateError(RuntimeError):
    """The model answered, but not with usable files."""


@dataclass(frozen=True)
class GenerateResult:
    files: dict
    check: BuildCheck

    @property
    def ok(self) -> bool:
        return self.check.ok


def build_messages(spec: Spec, requirements: tuple[Requirement, ...],
                   design: DesignResult) -> list[dict]:
    lines: list[str] = []
    data = spec.data
    lines.append("TARGET: " + str(data.get("target", "not given")))
    lines.append("KIND: " + str(data.get("kind", "not given")))
    if data.get("route"):
        lines.append("ROUTE: " + str(data["route"]))
    if data.get("caller"):
        lines.append("CALLER: " + str(data["caller"]))
    if data.get("profile"):
        lines.append("PROFILE: " + str(data["profile"]))
    if data.get("constraints"):
        lines.append("CONSTRAINTS: " + ", ".join(data["constraints"]))

    lines.append("")
    lines.append("REQUIREMENTS:")
    for r in requirements:
        lines.append(f"- {r.id} [{r.priority}] ({r.source.field}) {r.text}")

    lines.append("")
    lines.append("FILES:")
    for f in design.files:
        lines.append(f"- {f.path} (role: {f.role})")
        lines.append(f"  interface: {f.interface}")
        if f.requirements:
            lines.append(f"  serves: {', '.join(f.requirements)}")
        if f.measures:
            lines.append(f"  measures: {', '.join(f.measures)}")

    if design.gaps:
        lines.append("")
        lines.append("GAPS:")
        for g in design.gaps:
            lines.append(f"- {g.id} [{g.severity}] {g.text}")

    system, user = build_prompt(BUILD_PROMPT, spec.text, "\n".join(lines))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_files(answer: str) -> dict[str, str]:
    try:
        data = parse_json_response(answer)
    except ValueError as e:
        raise GenerateError(str(e)) from None
    if not isinstance(data.get("files"), dict):
        raise GenerateError('answer must be an object with a "files" object')
    files = data["files"]
    for path, content in files.items():
        if not isinstance(path, str) or not isinstance(content, str):
            raise GenerateError("every file must be a path mapped to text")
    return dict(files)


def generate_code(spec: Spec, requirements: tuple[Requirement, ...],
                  design: DesignResult,
                  chat_fn: Callable[..., str] = chat,
                  config: LLMConfig | None = None) -> GenerateResult:
    messages = build_messages(spec, requirements, design)
    answer = chat_fn(messages, config, max_tokens=MAX_TOKENS)
    files = parse_files(answer)
    return GenerateResult(files=files, check=check_build(design, requirements, files))


# ---------------------------------------------------------------- repair

def feedback_text(check: BuildCheck, verify) -> str:
    """The problems Verify and the build check found, as plain lines."""
    lines: list[str] = []
    for e in check.errors:
        lines.append(f"build: {e}")
    for f in check.files:
        for e in f.errors:
            lines.append(f"build: {f.path}: {e}")
    for r in verify.requirements:
        if r.status == "passed":
            continue
        lines.append(f"{r.id} [{r.priority}] is {r.status}" + (f" ({r.note})" if r.note else ""))
        for e in r.evidence:
            if e.status in ("fail", "error"):
                lines.append(f"  {e.source} {e.name}: {e.status} {e.detail}".rstrip())
    for p in verify.problems:
        lines.append(f"problem: {p}")
    if verify.analyzer and verify.analyzer.status == "failed":
        for f in verify.analyzer.findings:
            if f.level == "error":
                lines.append(f"analyzer {f.file}: {f.rule} {f.message}")
    return "\n".join(lines)


MAX_EARLIER_LINES = 12


def repair_code(spec: Spec, requirements: tuple[Requirement, ...], design: DesignResult,
                files: dict, check: BuildCheck, verify,
                chat_fn: Callable[..., str] = chat,
                config: LLMConfig | None = None,
                earlier: tuple[str, ...] = ()) -> GenerateResult:
    """One repair round: show the model its files and the problems, get new files.

    `earlier` is the problem text of the rounds before this one (the analog of Reflexion's memory): the model sees
    what was already tried and has not worked, so a fix does not undo the one before it.
    """
    messages = build_messages(spec, requirements, design)
    messages.append({"role": "assistant", "content": json.dumps({"files": files}, ensure_ascii=False)})
    text = load_prompt(REPAIR_PROMPT).strip() + "\n\nPROBLEMS:\n" + wrap_material("PROBLEMS", feedback_text(check, verify))
    if earlier:
        rounds = [f"round {n}:\n" + "\n".join(e.splitlines()[:MAX_EARLIER_LINES]) for n, e in enumerate(earlier, 1)]
        text += "\n\nEARLIER ROUNDS:\n" + wrap_material("EARLIER", "\n\n".join(rounds))
    messages.append({"role": "user", "content": text})
    answer = chat_fn(messages, config, max_tokens=MAX_TOKENS)
    new = parse_files(answer)
    return GenerateResult(files=new, check=check_build(design, requirements, new))
