"""One report shape for both products.

The analyser talks about findings, the validator about divergences, and a client
reading both should not have to learn two vocabularies. The shape below carries the
strictest verdict, the evidence behind it, and — this matters — the conditions under
which that verdict is true.

A verdict without conditions is a guess with a stamp on it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Level(str, Enum):
    SAFE = "SAFE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAIL = "FAIL"
    ERROR = "ERROR"


_RANK = {Level.SAFE: 0, Level.NEEDS_REVIEW: 1, Level.FAIL: 2, Level.ERROR: 3}


def strictest(levels: list[Level]) -> Level:
    """The verdict that survives a merge: the worst one, never the last one."""
    if not levels:
        return Level.SAFE
    return max(levels, key=lambda level: _RANK[level])


@dataclass
class Evidence:
    source: str
    detail: str
    location: str = ""

    def as_dict(self) -> dict:
        return {"source": self.source, "detail": self.detail, "location": self.location}


@dataclass
class Report:
    title: str
    level: Level
    summary: str = ""
    findings: list[Evidence] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    partial: bool = False
    stages: list[str] = field(default_factory=list)

    def merge(self, other: Report) -> Report:
        """Combine two reports without losing either side's evidence or conditions."""
        return Report(
            title=self.title or other.title,
            level=strictest([self.level, other.level]),
            summary=self.summary or other.summary,
            findings=[*self.findings, *other.findings],
            conditions=[*self.conditions, *other.conditions],
            partial=self.partial or other.partial,
            stages=[*self.stages, *other.stages],
        )

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "level": self.level.value,
            "summary": self.summary,
            "findings": [f.as_dict() for f in self.findings],
            "conditions": self.conditions,
            "partial": self.partial,
            "stages": self.stages,
        }

    def to_markdown(self) -> str:
        lines = [f"## {self.title}", "", f"**Level:** {self.level.value}"]
        if self.partial:
            lines.append("**Partial run:** not every stage ran; this verdict is not a proof.")
        if self.summary:
            lines += ["", self.summary]
        if self.findings:
            lines += ["", "### Findings"]
            for item in self.findings:
                where = f" — {item.location}" if item.location else ""
                lines.append(f"- **{item.source}**: {item.detail}{where}")
        if self.conditions:
            lines += ["", "### True under"]
            lines += [f"- {condition}" for condition in self.conditions]
        return "\n".join(lines)
