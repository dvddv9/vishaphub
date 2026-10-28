"""Pipeline: execute a plan, keep the session, stop when nothing improves.

Everything runs here, in this process. One URL means one deployment: the analyser's
rules and the validator's six stages are plain functions, so calling them over the
network would add a cold start and a second place where a key can be wrong, and buy
nothing.

The rules that make the loop honest:

* **nothing ran is not a pass.** An empty plan, a plan without stages, a stage that
  returned no verdict, or a stage that crashed all end in ERROR. `ok` is true only
  when the verdict is explicitly safe.
* **a crash stops the run.** A stage that cannot produce a verdict is not a stage that
  passed; later stages would be measuring a vacuum.
* **a FAIL verdict does not stop the run.** Failing tests and a security finding are
  different questions, and dangerous code must still reach the analyser. The verdict is
  the strictest seen, never the last one.
* **iterations stop early** when no stage changes its answer: the same words twice mean
  the next pass spends the same tokens for the same result.
* **verdicts are normalised.** Lower case, unknown words and an empty string are not
  silently ranked as safe — an unknown verdict is an ERROR, because a gate that cannot
  read its own answer must not open.
* every hop is appended to the trace, so the client can replay the run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import local
from .envelope import Envelope, Kind
from .router import Plan, Stage

log = logging.getLogger(__name__)

#: Rank decides which verdict survives a merge. Higher is stricter.
#: EMERGENCY sits above FAIL: a security signal must not be hidden by a failing test.
SEVERITY_ORDER = {
    "SAFE": 0,
    "PASS": 0,
    "NEEDS_REVIEW": 1,
    "REQUIRES_REVIEW": 1,
    "FAIL": 3,
    "EMERGENCY": 4,
    "ERROR": 5,
}

#: A run that ends in one of these did not pass its own gates.
BLOCKING_VERDICTS = {"FAIL", "ERROR", "EMERGENCY"}

#: Bounds. The router also caps iterations; this is the last line before a run starts.
MAX_MATERIAL = 200_000
MAX_FILES = 200
MAX_ITERATIONS = 3

#: Text shown to the client when an internal call fails. The real message goes to the log.
INTERNAL_ERROR = "an internal check failed; the run is not a pass"


def normalise(verdict: object) -> str:
    """Upper-case a verdict and reject anything the ranking does not know."""
    text = str(verdict or "").strip().upper()
    if text not in SEVERITY_ORDER:
        raise ValueError(f"unknown verdict: {verdict!r}")
    return text


def _rank(verdict: str) -> int:
    try:
        return SEVERITY_ORDER[normalise(verdict)]
    except ValueError:
        return SEVERITY_ORDER["ERROR"]


@dataclass
class Step:
    stage: str
    ok: bool
    verdict: str = ""
    detail: str = ""

    def as_dict(self) -> dict:
        return {"stage": self.stage, "ok": self.ok, "verdict": self.verdict, "detail": self.detail}


@dataclass
class RunResult:
    ok: bool
    verdict: str
    steps: list[Step] = field(default_factory=list)
    session_id: str = ""
    trace: list[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "verdict": self.verdict,
            "reason": self.reason,
            "session_id": self.session_id,
            "steps": [s.as_dict() for s in self.steps],
            "trace": self.trace,
        }


def _error(steps: list[Step], session_id: str, trace: list[str], reason: str) -> RunResult:
    return RunResult(False, "ERROR", steps, session_id, trace, reason)


def run_plan(plan: Plan, material: str = "", files: dict | None = None,
             spec: dict | None = None, filename: str = "input.txt") -> RunResult:
    """Execute the plan and return one honest verdict."""
    envelope = Envelope.build("hub", "analyser", Kind.QUESTION, {"filename": filename})
    steps: list[Step] = []
    trace = list(envelope.trace)
    files = files or {}
    spec = spec or {}

    # ---- gates: nothing to do is not a pass -------------------------------
    if not getattr(plan, "stages", None):
        return _error(steps, envelope.session_id, trace, "the plan has no stages; nothing would be checked")
    if int(getattr(plan, "iterations", 0) or 0) <= 0:
        return _error(steps, envelope.session_id, trace, "iterations must be at least 1")
    if int(plan.iterations) > MAX_ITERATIONS:
        return _error(steps, envelope.session_id, trace, f"iterations above {MAX_ITERATIONS} are refused")
    if len(material) > MAX_MATERIAL:
        return _error(steps, envelope.session_id, trace, f"material above {MAX_MATERIAL} characters is refused")
    if len(files) > MAX_FILES:
        return _error(steps, envelope.session_id, trace, f"more than {MAX_FILES} files is refused")

    strictest: str | None = None
    previous: dict[str, str] = {}

    for pass_no in range(1, int(plan.iterations) + 1):
        current: dict[str, str] = {}

        for stage in plan.stages:
            if stage is Stage.GENERATOR:
                steps.append(Step("generator", False, detail="generation is not wired into this process"))
                return _error(steps, envelope.session_id, trace,
                              "generation is not available in this deployment")

            if stage is Stage.VALIDATOR:
                if not files:
                    steps.append(Step("validator", False, detail="no files supplied"))
                    return _error(steps, envelope.session_id, trace,
                                  "validation needs files; nothing was sent")
                result = local.validate_code(files, spec)
                if not result.get("ok"):
                    log.warning("validator failed: %s", result.get("error"))
                    steps.append(Step("validator", False, detail=INTERNAL_ERROR))
                    return _error(steps, envelope.session_id, trace,
                                  "validator failed; the deliverable is unverified")
                report = result.get("report") or {}
                try:
                    verdict = normalise(report.get("verdict"))
                except ValueError:
                    log.warning("validator returned an unusable verdict: %r", report.get("verdict"))
                    steps.append(Step("validator", False, verdict="",
                                      detail="the report carried no usable verdict"))
                    return _error(steps, envelope.session_id, trace,
                                  "validator returned no verdict; nothing was verified")
                current["validator"] = verdict
                steps.append(Step("validator", verdict not in BLOCKING_VERDICTS,
                                  verdict, detail=f"{report.get('finding_count', 0)} findings"))
                trace.append(f"pass {pass_no} validator -> {verdict}")
                if strictest is None or _rank(verdict) > _rank(strictest):
                    strictest = verdict
                continue

            if stage is Stage.ANALYSER:
                if not material.strip():
                    steps.append(Step("analyser", False, detail="no material supplied"))
                    return _error(steps, envelope.session_id, trace,
                                  "analysis needs material; nothing was sent")
                result = local.analyse_static(material)
                if not result.get("ok"):
                    log.warning("analyser failed: %s", result.get("error"))
                    steps.append(Step("analyser", False, detail=INTERNAL_ERROR))
                    return _error(steps, envelope.session_id, trace,
                                  "analyser failed; no security verdict available")
                try:
                    verdict = normalise(result.get("verdict"))
                except ValueError:
                    log.warning("analyser returned an unusable verdict: %r", result.get("verdict"))
                    steps.append(Step("analyser", False, verdict="",
                                      detail="the result carried no usable verdict"))
                    return _error(steps, envelope.session_id, trace,
                                  "analyser returned no verdict; no security answer available")
                current["analyser"] = verdict
                found = len(result.get("findings") or [])
                steps.append(Step("analyser", True, verdict,
                                  detail=f"{found} findings · rules only" if found else "rules only, nothing matched"))
                trace.append(f"pass {pass_no} analyser -> {verdict}")
                if strictest is None or _rank(verdict) > _rank(strictest):
                    strictest = verdict
                continue

        if int(plan.iterations) > 1 and previous and current == previous:
            trace.append(f"stop after pass {pass_no}: no stage changed its verdict")
            break
        previous = current

    # ---- nothing produced a verdict: this is a failure, not a pass --------
    if strictest is None:
        return _error(steps, envelope.session_id, trace,
                      "no stage produced a verdict; an empty run is not a pass")

    final = strictest
    # `ok` answers «did the run survive its own gates», not «is the material clean»:
    # REQUIRES_REVIEW is a successful run that found something.
    ok = final not in BLOCKING_VERDICTS
    reason = plan.note or ("strictest verdict across passes" if int(plan.iterations) > 1 else "")
    if final == "EMERGENCY":
        reason = (reason + " · " if reason else "") + "an emergency-level security signal is present"
    return RunResult(ok, final, steps, envelope.session_id, trace, reason)
