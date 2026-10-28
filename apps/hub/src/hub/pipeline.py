"""Pipeline: execute a plan, keep the session, stop when nothing improves.

Everything runs here, in this process. One URL means one deployment: the analyser's
rules and the validator's six stages are plain functions, so calling them over the
network would add a cold start and a second place where a key can be wrong, and buy
nothing.

The rules that make the loop honest:

* a stage that fails stops the run — a generator error cannot become a validator pass;
* iterations stop early when no stage changes its answer: the same words twice mean the
  next pass spends the same tokens for the same result;
* the final verdict is the strictest one seen, not the last one: a later «SAFE» does
  not erase an earlier «REQUIRES_REVIEW»;
* every hop is appended to the trace, so the client can replay the run.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import local
from .envelope import Envelope, Kind
from .router import Plan, Stage

SEVERITY_ORDER = {"ERROR": 4, "FAIL": 4, "EMERGENCY": 3, "REQUIRES_REVIEW": 2, "NEEDS_REVIEW": 2, "PASS": 1, "SAFE": 0, "": 0}

#: Verdicts that describe the analyser; everything else describes the pipeline.
ANALYSER_VERDICTS = {"SAFE", "REQUIRES_REVIEW", "EMERGENCY"}


def _rank(verdict: str) -> int:
    return SEVERITY_ORDER.get((verdict or "").upper(), 2)


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


def run_plan(plan: Plan, material: str = "", files: dict | None = None,
             spec: dict | None = None, filename: str = "input.txt") -> RunResult:
    """Execute the plan and return one honest verdict."""
    envelope = Envelope.build("hub", "analyser", Kind.QUESTION, {"filename": filename})
    steps: list[Step] = []
    trace = list(envelope.trace)
    strictest: str | None = None
    files = files or {}
    spec = spec or {}

    previous: dict[str, str] = {}
    for pass_no in range(1, plan.iterations + 1):
        current: dict[str, str] = {}

        for stage in plan.stages:
            if stage is Stage.GENERATOR:
                steps.append(Step("generator", False,
                                  detail="generation needs a model and a workspace; not wired into this process"))
                return RunResult(False, "ERROR", steps, envelope.session_id, trace,
                                 "generation is not available in this deployment")

            if stage is Stage.VALIDATOR:
                if not files:
                    steps.append(Step("validator", False, detail="no files supplied"))
                    return RunResult(False, "ERROR", steps, envelope.session_id, trace,
                                     "validation needs files; nothing was sent")
                result = local.validate_code(files, spec)
                if not result["ok"]:
                    steps.append(Step("validator", False, detail=result["error"]))
                    return RunResult(False, "ERROR", steps, envelope.session_id, trace,
                                     "validator failed; the deliverable is unverified")
                report = result["report"]
                verdict = report.get("verdict", "")
                current["validator"] = verdict
                steps.append(Step("validator", verdict in ("PASS", "NEEDS_REVIEW"), verdict,
                                  detail=f"{report.get('finding_count', 0)} findings"))
                trace.append(f"pass {pass_no} validator -> {verdict}")
                if strictest is None or _rank(verdict) > _rank(strictest):
                    strictest = verdict
                continue

            if stage is Stage.ANALYSER:
                if not material.strip():
                    steps.append(Step("analyser", False, detail="no material supplied"))
                    return RunResult(False, "ERROR", steps, envelope.session_id, trace,
                                     "analysis needs material; nothing was sent")
                result = local.analyse_static(material)
                if not result["ok"]:
                    steps.append(Step("analyser", False, detail=result["error"]))
                    return RunResult(False, "ERROR", steps, envelope.session_id, trace,
                                     "analyser failed; no security verdict available")
                verdict = result.get("verdict") or ""
                current["analyser"] = verdict
                found = len(result.get("findings") or [])
                steps.append(Step("analyser", True, verdict,
                                  detail=f"{found} findings · rules only" if found else "rules only, nothing matched"))
                trace.append(f"pass {pass_no} analyser -> {verdict}")
                if strictest is None or _rank(verdict) > _rank(strictest):
                    strictest = verdict
                continue

        if plan.iterations > 1 and previous and current == previous:
            trace.append(f"stop after pass {pass_no}: no stage changed its verdict")
            break
        previous = current

    final = strictest or "PASS"
    ok = final not in ("FAIL", "ERROR", "EMERGENCY")
    return RunResult(ok, final, steps, envelope.session_id, trace,
                     plan.note or ("strictest verdict across passes" if plan.iterations > 1 else ""))
