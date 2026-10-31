"""Three results that must never be read as one.

* **risk verdict** (`verdict`): what the rules, the tests and the model together say about the
  material. SAFE/PASS, NEEDS_REVIEW/REQUIRES_REVIEW, FAIL, EMERGENCY, ERROR (see `verdicts.py`).
* **fix status**: what is known about a proposed fix. It complements the risk verdict and never
  softens it: a verified fix does not turn FAIL into PASS, the material that was sent is still the
  material that was sent.
* **verification status**: how much of the planned checking really ran, and under what isolation.

What stands behind each verdict is named in `basis`: *rules* (the analyser's static rules),
*tests* (the validator running the deliverable's own tests), *model* (a recommendation, merged last
and only upwards). A verdict that rests on the model alone is a guess, and says so.
"""
from __future__ import annotations

NO_PATCH = "NO_PATCH"
FIX_UNVERIFIED = "FIX_UNVERIFIED"
FIX_VERIFIED = "FIX_VERIFIED"
FIX_PARTIAL = "FIX_PARTIAL"
FIX_REJECTED = "FIX_REJECTED"
FIX_STATUSES = (NO_PATCH, FIX_UNVERIFIED, FIX_VERIFIED, FIX_PARTIAL, FIX_REJECTED)

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
NOT_RUN = "NOT_RUN"
ERROR = "ERROR"
VERIFICATION_STATUSES = (COMPLETE, PARTIAL, NOT_RUN, ERROR)

_CHECKED_STAGES = ("analyser", "validator")


def _verdict_of(checks: dict, name: str) -> str | None:
    one = (checks or {}).get(name)
    return (one or {}).get("verdict") or None


def risk(verdict: str, checks: dict, model_verdict: str) -> dict:
    """The verdict and what it rests on. The model can only raise it, never lower it."""
    basis = {"rules": _verdict_of(checks, "analyser"), "tests": _verdict_of(checks, "validator"),
             "model": model_verdict or None}
    grounded = bool(basis["rules"] or basis["tests"])
    return {"verdict": verdict, "basis": basis, "rests_on_model_alone": bool(basis["model"]) and not grounded}


def fix(patch: dict, checked: dict | None = None) -> dict:
    """Status of a proposed fix. `checked` is the result of a real patch check, when one ran."""
    if checked:
        status = checked.get("status")
        if status not in FIX_STATUSES:
            raise ValueError(f"unknown fix status: {status!r}")
        return {"status": status, "reason": str(checked.get("reason") or ""), **{
            k: v for k, v in checked.items() if k not in ("status", "reason")}}
    if not patch:
        return {"status": NO_PATCH, "reason": "no patch was proposed"}
    return {"status": FIX_UNVERIFIED,
            "reason": "a patch was proposed by the model; it was not applied to a snapshot and re-checked"}


def verification(ok: bool, verdict: str, checks: dict, plan: dict, not_checked: list) -> dict:
    ran = [name for name in _CHECKED_STAGES if (checks or {}).get(name)]
    planned = [s for s in (plan or {}).get("stages", []) if s in _CHECKED_STAGES]
    not_run = sorted(set(planned) - set(ran))
    isolation = ((checks or {}).get("validator") or {}).get("isolation")
    if not ran:
        status = ERROR if verdict == "ERROR" else NOT_RUN
    elif (plan or {}).get("partial") or not_checked or not_run:
        status = PARTIAL
    else:
        status = COMPLETE
    return {"status": status, "ran": ran, "not_run": not_run, "isolation": isolation,
            "not_checked": list(not_checked or [])}


def compute(*, ok: bool, verdict: str, checks: dict, plan: dict, patch: dict, model_verdict: str,
            not_checked: list, patch_check: dict | None = None) -> dict:
    return {
        "risk": risk(verdict, checks, model_verdict),
        "fix": fix(patch, patch_check),
        "verification": verification(ok, verdict, checks, plan, not_checked),
    }