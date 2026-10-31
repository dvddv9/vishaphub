"""The CI contract: one place decides what a run means for a pipeline, for the CLI and the HTTP door alike.

`decide(result, fail_on, require_complete)` turns a run (the dict the API returns) into an exit code and
the reasons. A pipeline needs three things that a verdict alone does not give it:

* a threshold: which verdict fails the build (`fail_on`: review, fail or emergency; default fail);
* a way to refuse a green that checked nothing: with `require_complete`, a run whose verification is not
  COMPLETE does not pass, whatever its verdict says. An empty or partial run must not look like a success;
* a code a shell can branch on, and the reasons in words.

Exit codes (stable): 0 pass, 1 the verdict or the run failed, 2 bad usage (the CLI's own), 3 the checking
was incomplete (only with `require_complete`). A failing verdict wins over incompleteness.
The contract is versioned: `schema` is "vishap.run/1". New fields may appear; a field is never removed or
changed in meaning without a new schema.
"""
from __future__ import annotations

from . import statuses
from .verdicts import SEVERITY_ORDER, rank

SCHEMA = "vishap.run/1"
FAIL_ON = ("review", "fail", "emergency")
DEFAULT_FAIL_ON = "fail"
_THRESHOLD = {"review": SEVERITY_ORDER["REQUIRES_REVIEW"], "fail": SEVERITY_ORDER["FAIL"],
              "emergency": SEVERITY_ORDER["EMERGENCY"]}

EXIT_PASS, EXIT_FAIL, EXIT_USAGE, EXIT_INCOMPLETE = 0, 1, 2, 3


def decide(result: dict, fail_on: str = DEFAULT_FAIL_ON, require_complete: bool = False,
           require_measured: bool = False) -> dict:
    if fail_on not in FAIL_ON:
        raise ValueError(f"fail_on must be one of {', '.join(FAIL_ON)}")
    verdict = str((result or {}).get("verdict") or "")
    stat = (result or {}).get("statuses") or {}
    ver = stat.get("verification") or {}
    verification = str(ver.get("status") or "")
    fix = str((stat.get("fix") or {}).get("status") or "")
    reasons: list[str] = []
    failed = False
    if not (result or {}).get("ok"):
        failed = True
        reasons.append("the run did not pass its own gates: "
                       + str(result.get("reason") or result.get("error") or "no reason given"))
    elif rank(verdict) >= _THRESHOLD[fail_on]:        # an unreadable verdict ranks as ERROR: it fails
        failed = True
        reasons.append(f"verdict {verdict or '(none)'} is at or above the failing level '{fail_on}'")
    complete = verification == statuses.COMPLETE
    if require_complete and not complete and not failed:
        reasons.append(f"the checking was {verification or 'unknown'}: ran "
                       f"{', '.join(ver.get('ran') or []) or 'nothing'}; not run "
                       f"{', '.join(ver.get('not_run') or []) or 'nothing listed'}")
    langs = [x for x in (((result or {}).get("checks") or {}).get("analyser") or {}).get("languages") or []]
    unmeasured = [x for x in langs if x.get("adequacy") != "measured"]
    if require_measured and unmeasured and not failed:
        reasons.append("the rules are not measured well enough for: " + "; ".join(
            f"{x.get('language')} ({x.get('adequacy')}: {x.get('dangerous_examples', 0)} dangerous, "
            f"{x.get('safe_examples', 0)} safe labelled examples)" for x in unmeasured))
    stop = (require_complete and not complete) or (require_measured and bool(unmeasured))
    code = EXIT_FAIL if failed else (EXIT_INCOMPLETE if stop else EXIT_PASS)
    return {"schema": SCHEMA, "pass": code == EXIT_PASS, "exit_code": code, "fail_on": fail_on,
            "require_complete": bool(require_complete), "verdict": verdict, "fix": fix,
            "verification": verification, "complete": complete, "require_measured": bool(require_measured),
            "languages": {x.get("language"): x.get("adequacy") for x in langs}, "reasons": reasons}