"""Intake: spec.yaml -> numbered requirements. Rules only, no LLM."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from .spec import REQUIREMENT_LISTS, Spec, load_spec

PRIORITY = {
    "must_never": "critical",
    "inputs": "high",
    "outputs": "high",
    "should": "high",
    "may": "medium",
}

VERIFY = {
    "inputs": ("rule", "test"),
    "outputs": ("test",),
    "must_never": ("rule", "test"),
    "should": ("test",),
    "may": ("test",),
}


@dataclass(frozen=True)
class Source:
    field: str
    line: int


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    priority: str
    source: Source
    verify: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "priority": self.priority,
            "source": {"field": self.source.field, "line": self.source.line},
            "verify": list(self.verify),
        }


@dataclass(frozen=True)
class IntakeResult:
    spec_sha256: str
    updated: dt.date
    requirements: tuple[Requirement, ...]

    def to_dict(self) -> dict:
        return {
            "spec_sha256": self.spec_sha256,
            "updated": self.updated.isoformat(),
            "requirements": [r.to_dict() for r in self.requirements],
        }


def _text_for(field: str, item: dict) -> str:
    if field == "inputs":
        rule = item.get("rule")
        head = f"Input {item['name']} ({item['in']})"
        return f"{head}: {rule}" if rule else f"{head} is required"
    if field == "outputs":
        if item.get("body"):
            return f"Status {item['status']} returns {item['body']}"
        return f"Status {item['status']} when {item['when']}"
    return item["text"]


def requirements_from(spec: Spec) -> tuple[Requirement, ...]:
    out: list[Requirement] = []
    n = 0
    for field in REQUIREMENT_LISTS:
        for item, line in spec.items.get(field, []):
            n += 1
            out.append(Requirement(
                id=f"R{n}",
                text=_text_for(field, item),
                priority=PRIORITY[field],
                source=Source(field=field, line=line),
                verify=VERIFY[field],
            ))
    return tuple(out)


def intake(path: str | Path) -> IntakeResult:
    spec = load_spec(path)
    return IntakeResult(
        spec_sha256=spec.sha256,
        updated=spec.updated,
        requirements=requirements_from(spec),
    )
