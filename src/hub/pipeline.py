"""Pipeline: execute a plan, keep the session, stop when nothing improves.

The rules that make the loop honest:

* a stage that fails stops the run — a generator error cannot become a validator pass;
* iterations stop early when the analyser verdict stops improving: three identical
  verdicts in a row mean the fourth pass will spend tokens for the same answer;
* the final verdict is the strictest one seen, not the last one: a later «SAFE» does
  not erase an earlier «REQUIRES_REVIEW»;
* every hop is appended to the envelope trace, so the client can replay the run.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .envelope import Envelope, Kind
from .router import Plan, Stage
from .services import ServiceConfig, analyse, generate, validate

SEVERITY_ORDER = {"ERROR": 4, "FAIL": 4, "EMERGENCY": 3, "REQUIRES_REVIEW": 2, "NEEDS_REVIEW": 2, "PASS": 1, "SAFE": 0, "": 0}


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


def run_plan(cfg: ServiceConfig, plan: Plan, material: str, spec: str = "",
             filename: str = "input.txt", out_dir: str = "", validator_spec: dict | None = None) -> RunResult:
    """Execute the plan and return one honest verdict."""
    envelope = Envelope.build("hub", "generator" if Stage.GENERATOR in plan.stages else "analyser",
                              Kind.QUESTION, {"filename": filename})
    steps: list[Step] = []
    trace = list(envelope.trace)
    strictest = "PASS"

    for pass_no in range(1, plan.iterations + 1):
        verdicts: list[str] = []
        for stage in plan.stages:
            if stage is Stage.GENERATOR:
                if not spec:
                    steps.append(Step("generator", False, detail="no spec supplied; generation skipped"))
                    return RunResult(False, "ERROR", steps, envelope.session_id, trace,
                                     "generation needs a spec")
                result = generate(cfg, spec, out_dir)
                if not result["ok"]:
                    steps.append(Step("generator", False, detail=result["error"]))
                    return RunResult(False, "ERROR", steps, envelope.session_id, trace,
                                     "generator failed; later stages would validate nothing")
                out_dir = result["out_dir"]
                steps.append(Step("generator", True, detail=f"deliverable at {out_dir}"))
                trace.append(f"pass {pass_no} generator -> {out_dir}")
                continue

            if stage is Stage.VALIDATOR:
                result = validate(cfg, out_dir, validator_spec or {})
                if not result["ok"]:
                    steps.append(Step("validator", False, detail=result["error"]))
                    return RunResult(False, "ERROR", steps, envelope.session_id, trace,
                                     "validator failed; the deliverable is unverified")
                report = result["report"]
                verdict = report.get("verdict", "")
                verdicts.append(verdict)
                steps.append(Step("validator", verdict in ("PASS", "NEEDS_REVIEW"), verdict,
                                  detail=f"{report.get('finding_count', 0)} findings"))
                trace.append(f"pass {pass_no} validator -> {verdict}")
                if verdict == "FAIL":
                    strictest = "FAIL"
                continue

            if stage is Stage.ANALYSER:
                result = analyse(cfg, material, filename)
                if not result["ok"]:
                    steps.append(Step("analyser", False, detail=result["error"]))
                    return RunResult(False, "ERROR", steps, envelope.session_id, trace,
                                     "analyser failed; no security verdict available")
                verdict = result.get("verdict") or result.get("risk_verdict") or ""
                verdicts.append(verdict)
                steps.append(Step("analyser", True, verdict,
                                  detail=", ".join(result.get("cwe_ids") or []) or "no CWE"))
                trace.append(f"pass {pass_no} analyser -> {verdict}")
                if _rank(verdict) > _rank(strictest):
                    strictest = verdict
                continue

        if plan.iterations > 1 and len(verdicts) >= 2 and len(set(verdicts)) == 1:
            trace.append(f"stop after pass {pass_no}: verdicts stopped changing ({verdicts[-1]})")
            break

    ok = strictest not in ("FAIL", "ERROR", "EMERGENCY")
    return RunResult(ok, strictest, steps, envelope.session_id, trace,
                     plan.note or ("strictest verdict across passes" if plan.iterations > 1 else ""))
