"""Gaps: what the spec leaves out or contradicts.

Deterministic rules over the structured fields only. Reading the free
`text` against the requirements needs an LLM and comes in a later step;
until then a fact stated only in `text` still counts as missing here.

Types and severity:
  missing_input  critical  something Design or Verify needs is not given
  contradiction  critical  two parts of the spec cannot both hold
  assumption     noted     the run goes on with a stated default
"""

from __future__ import annotations

from dataclasses import dataclass

from generator.pipeline.intake import Source
from generator.tools.spec import Spec

SEVERITY = {
    "missing_input": "critical",
    "contradiction": "critical",
    "assumption": "noted",
}

# Statuses that answer "what happens on invalid input".
INVALID_INPUT_STATUSES = frozenset({400, 422})


@dataclass(frozen=True)
class Gap:
    id: str
    type: str
    severity: str
    text: str
    source: Source | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "severity": self.severity,
            "text": self.text,
            "source": (
                {"field": self.source.field, "line": self.source.line}
                if self.source else None
            ),
        }


def _src(spec: Spec, key: str) -> Source | None:
    line = spec.key_lines.get(key)
    return Source(field=key, line=line) if line else None


def collect(spec: Spec) -> list[tuple[str, str, Source | None]]:
    data = spec.data
    found: list[tuple[str, str, Source | None]] = []

    def add(kind: str, text: str, source: Source | None) -> None:
        found.append((kind, text, source))

    for key in ("target", "kind", "output"):
        if key not in data:
            add("missing_input", f"{key} is not given, so the files cannot be planned", None)

    kind = data.get("kind")
    inputs = spec.items.get("inputs", [])
    outputs = spec.items.get("outputs", [])
    constraints = set(data.get("constraints") or [])

    if kind == "http-endpoint" and "caller" not in data:
        add("missing_input",
            "who calls the endpoint is not given (caller: public, signed-in or internal)",
            _src(spec, "kind"))

    has_rule = any(item.get("rule") for item, _ in inputs)
    answers_invalid = any(item.get("status") in INVALID_INPUT_STATUSES for item, _ in outputs)
    if kind == "http-endpoint" and has_rule and not answers_invalid:
        add("missing_input",
            "the response to invalid input is not given (no 400 or 422 in outputs)",
            _src(spec, "outputs") or _src(spec, "inputs"))

    for item, line in inputs:
        if item.get("rule"):
            continue
        if "validate-inputs" in constraints:
            add("missing_input",
                f"input {item['name']} has no rule, but validate-inputs is required",
                Source("inputs", line))
        else:
            add("assumption",
                f"input {item['name']} has no rule, so any value is accepted",
                Source("inputs", line))

    if "profile" not in data:
        add("assumption", "profile is not given, so no security baseline is applied", None)
    if "check" not in data:
        add("assumption", "check is not given, so the Analyzer runs on the result", None)

    profile = data.get("profile") or ""
    if profile.startswith("owasp-asvs") and data.get("check") == "none":
        add("contradiction",
            f"profile {profile} needs the result checked, but check is none",
            _src(spec, "check"))

    never = {item["text"].strip().lower(): line
             for item, line in spec.items.get("must_never", [])}
    for field in ("should", "may"):
        for item, line in spec.items.get(field, []):
            hit = never.get(item["text"].strip().lower())
            if hit is not None:
                add("contradiction",
                    f"\"{item['text']}\" is in must_never (line {hit}) and in {field}",
                    Source(field, line))

    return found


def number(found: list[tuple[str, str, Source | None]]) -> tuple[Gap, ...]:
    return tuple(
        Gap(id=f"G{n}", type=kind, severity=SEVERITY[kind], text=text, source=source)
        for n, (kind, text, source) in enumerate(found, 1)
    )


def find_gaps(spec: Spec) -> tuple[Gap, ...]:
    return number(collect(spec))
