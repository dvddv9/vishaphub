"""Core data types for the Vishap validator.

The validator answers one question: does the generated code do what the spec
promised? It never re-audits security — that is the analyser's job — and it never
rewrites the code. It compares, records findings, and returns a verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Verdict(str, Enum):
    PASS = "PASS"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAIL = "FAIL"
    ERROR = "ERROR"


@dataclass
class Finding:
    """One concrete divergence between spec and code."""

    check: str
    severity: Severity
    message: str
    location: str = ""

    def as_dict(self) -> dict:
        return {
            "check": self.check,
            "severity": self.severity.value,
            "message": self.message,
            "location": self.location,
        }


@dataclass
class CheckResult:
    """What one check produced."""

    name: str
    ok: bool
    findings: list[Finding] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "findings": [f.as_dict() for f in self.findings],
        }


@dataclass
class Spec:
    """What the code was supposed to be.

    ``files``      — relative paths the deliverable must contain.
    ``exports``    — names that must be importable from the package entry point.
    ``tests``      — test file paths that must run and pass.
    ``entry``      — the file that exposes the public API (default: package root).
    """

    language: str = "python"
    files: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    entry: str = ""


@dataclass
class Report:
    """Result of a whole validation run."""

    verdict: Verdict
    checks: list[CheckResult] = field(default_factory=list)
    reason: str = ""

    @property
    def findings(self) -> list[Finding]:
        return [f for c in self.checks for f in c.findings]

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "reason": self.reason,
            "checks": [c.as_dict() for c in self.checks],
            "finding_count": len(self.findings),
        }
