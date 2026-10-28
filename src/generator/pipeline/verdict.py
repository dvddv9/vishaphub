"""Verdicts: the single source of truth for what a result means.

The analog of Vishap's `pipeline/verdict.py`. Verify collects evidence; this file turns evidence into
a status per requirement, statuses into a verdict for the code, and the spec's age into a verdict for the
spec. Nothing else decides "passed".
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from generator.config import COVERAGE_MIN, STALE_DAYS
from generator.tools.analyzer import AnalyzerResult


@dataclass(frozen=True)
class Evidence:
    source: str     # model-test | attack | rule
    name: str
    status: str     # pass | fail | error | skipped
    detail: str = ""
    cwe: str = ""   # set by a static rule (see tools/static_scan.py)

    def to_dict(self) -> dict:
        d = {"source": self.source, "name": self.name,
             "status": self.status, "detail": self.detail}
        if self.cwe:
            d["cwe"] = self.cwe
        return d


@dataclass(frozen=True)
class RequirementVerdict:
    id: str
    priority: str
    status: str     # passed | failed | needs_verification | not_verified
    evidence: tuple[Evidence, ...]
    note: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "priority": self.priority, "status": self.status,
                "note": self.note, "evidence": [e.to_dict() for e in self.evidence]}


@dataclass(frozen=True)
class VerifyResult:
    requirements: tuple[RequirementVerdict, ...]
    code_verdict: str           # passed | failed | needs_verification
    spec_stale: bool
    spec_age_days: int
    coverage_status: str        # ok | below | skipped
    coverage_percent: float | None
    coverage_note: str
    problems: tuple[str, ...]
    notes: tuple[str, ...] = ()
    analyzer: AnalyzerResult | None = None
    coverage_min: float = COVERAGE_MIN
    stale_days: int = STALE_DAYS

    @property
    def passed(self) -> int:
        return sum(1 for r in self.requirements if r.status == "passed")

    def to_dict(self) -> dict:
        return {
            "code_verdict": self.code_verdict,
            "spec": {"stale": self.spec_stale, "age_days": self.spec_age_days,
                     "stale_after_days": self.stale_days},
            "coverage": {"status": self.coverage_status, "percent": self.coverage_percent,
                         "minimum": self.coverage_min, "note": self.coverage_note},
            "problems": list(self.problems),
            "notes": list(self.notes),
            "analyzer": self.analyzer.to_dict() if self.analyzer else None,
            "requirements": [r.to_dict() for r in self.requirements],
        }


def decide_requirement(evidence: list[Evidence]) -> tuple[str, str]:
    own = [e for e in evidence if e.source in ("attack", "rule") and e.status in ("pass", "fail")]
    model = [e for e in evidence if e.source == "model-test" and e.status != "skipped"]
    if any(e.status == "fail" for e in own):
        return "failed", ""
    model_bad = [e for e in model if e.status != "pass"]
    if model_bad and own:
        return "needs_verification", "a model test fails while Verify's own checks pass; the test may be wrong"
    if model_bad:
        return "failed", ""
    if model or own:
        return "passed", ""
    return "not_verified", "no test or check covers it"


def compute_code_verdict(verdicts: list[RequirementVerdict] | tuple[RequirementVerdict, ...],
                         coverage_status: str, problems: list[str] | tuple[str, ...],
                         analyzer_failed: bool = False) -> str:
    """failed | needs_verification | passed.

    `failed`: a critical or high requirement failed, or the analyzer found errors.
    `needs_verification`: something critical or high is not proven, coverage is below the minimum,
    or Verify could not run something. `passed` only when all of that is clean.
    """
    hard = [v for v in verdicts if v.priority in ("critical", "high")]
    if any(v.status == "failed" for v in hard) or analyzer_failed:
        return "failed"
    if any(v.status != "passed" for v in hard) or coverage_status == "below" or problems:
        return "needs_verification"
    return "passed"


def compute_spec_verdict(age_days: int, stale_days: int = STALE_DAYS) -> tuple[bool, int]:
    """(stale, age). A spec not updated for more than `stale_days` days is stale."""
    return age_days > stale_days, age_days


def apply_build_errors(result: VerifyResult, build_errors: list[str]) -> VerifyResult:
    """A clean run over a build with errors is not a pass: Verify ran what it could."""
    if not build_errors or result.code_verdict != "passed":
        return result
    return dataclasses.replace(
        result, code_verdict="needs_verification",
        notes=result.notes + ("build check reported errors: " + "; ".join(build_errors[:3]),))
