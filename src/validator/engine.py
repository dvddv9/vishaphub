"""Engine: run the checks in order and turn findings into one verdict.

Order matters. Structure and syntax stop the run: behaviour on code that does not
parse is noise. Contract then behaviour, because "the name is missing" explains a
failing test better than the traceback does.

Verdict rules:

* any CRITICAL finding        -> FAIL
* any HIGH finding            -> NEEDS_REVIEW
* only MEDIUM/LOW             -> NEEDS_REVIEW
* nothing                     -> PASS
* an exception in the engine  -> ERROR (never PASS: a check that did not run
                                 must not look like a check that passed)
"""
from __future__ import annotations

from .checks import behavior, contract, structure, syntax
from .models import CheckResult, Report, Severity, Spec, Verdict

ORDER = (structure, syntax, contract, behavior)
STOP_ON_FAILURE = {"structure", "syntax"}


def validate(root: str, spec: Spec) -> Report:
    checks: list[CheckResult] = []
    try:
        for module in ORDER:
            result = module.run(root, spec)
            checks.append(result)
            if not result.ok and module.__name__.rsplit(".", 1)[-1] in STOP_ON_FAILURE:
                reason = f"stopped after {result.name}: later checks would be noise"
                return Report(verdict=_verdict(checks), checks=checks, reason=reason)
    except Exception as exc:  # noqa: BLE001 - surface it as ERROR, never as PASS
        checks.append(
            CheckResult(
                name="engine",
                ok=False,
                findings=[],
                skip_reason=f"{type(exc).__name__}: {exc}",
            )
        )
        return Report(verdict=Verdict.ERROR, checks=checks, reason="validator crashed")

    return Report(verdict=_verdict(checks), checks=checks)


def _verdict(checks: list[CheckResult]) -> Verdict:
    findings = [f for c in checks for f in c.findings]
    if any(f.severity is Severity.CRITICAL for f in findings):
        return Verdict.FAIL
    if findings:
        return Verdict.NEEDS_REVIEW
    if any(not c.ok for c in checks):
        return Verdict.NEEDS_REVIEW
    return Verdict.PASS
