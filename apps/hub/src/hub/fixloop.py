"""The checking loop: the model proposes a patch, the hub checks it, a refusal tells the model why.

The model never decides anything here. Every attempt goes through `patchcheck.check` (a bounded diff applied
to a copy, the rules re-run, the deliverable's own tests and the trusted exploit probes run in a confirmed
isolation), and the status comes from that check, not from what the model says about its own patch.

* at most three attempts in all (the patch the run already has counts as the first; at most two more
  model calls);
* a rejected or partial patch goes back to the model with the concrete reason, and the patch it was about;
* FIX_VERIFIED ends the loop. FIX_UNVERIFIED ends it too: the checks cannot run here, and asking the model
  again would spend money on an answer nobody can check;
* the same patch twice, no patch, or a model that cannot answer ends it with that reason;
* the model cannot delete trusted tests, touch the test configuration or weaken the rules: the first is
  refused by the patch check (`FIX_REJECTED`), the others are not its to change. It cannot lower the risk
  verdict either: the verdict is merged upward only, and a fix status never changes it;
* after three failures the answer is the best status reached (PARTIAL over REJECTED), never a promise.
"""
from __future__ import annotations

from . import patchcheck, statuses

MAX_ATTEMPTS = 3
MAX_PREVIOUS_CHARS = 12_000

_RANK = {statuses.FIX_VERIFIED: 3, statuses.FIX_PARTIAL: 2, statuses.FIX_REJECTED: 1, statuses.FIX_UNVERIFIED: 0}


def feedback(n: int, limit: int, patch: dict, result: dict) -> str:
    """What the model is told after a patch was not accepted: the status, the reason, the patch, the rules."""
    shown = "\n\n".join(f"--- {name}\n{text}" for name, text in sorted(patch.items()))
    if len(shown) > MAX_PREVIOUS_CHARS:
        shown = shown[:MAX_PREVIOUS_CHARS] + "\n[cut]"
    return (
        f"\n\nFix check, attempt {n} of {limit}: your patch was applied to a copy of the files and checked "
        f"by the hub. Result: {result['status']}. Reason: {result['reason']}\n"
        "Do not change test files, test configuration or the checks themselves; a patch that does is "
        "refused. Propose a corrected patch (whole files) that fixes the problem and keeps the "
        f"tests passing.\n\nYour previous patch:\n{shown}"
    )


def _row(n: int, source: str, patch: dict, result: dict) -> dict:
    return {"n": n, "source": source, "diff_sha256": result.get("diff_sha256") or patchcheck.sha(patch),
            "files": sorted(patch), "status": result["status"], "reason": result["reason"]}


def run(snapshot: dict, spec: dict, first_patch: dict, ask, *, max_attempts: int = MAX_ATTEMPTS,
        check=None) -> dict:
    """Check `first_patch`; while it is rejected or partial, ask again with the reason, up to the limit.

    `ask(feedback_text) -> dict` is one model call (the answer of `proposal.propose`). `check` defaults to
    `patchcheck.check`. Returns {"status", "reason", "patch", "patch_check", "attempts", "stop_reason",
    "model_calls"}; `patch` and `patch_check` are those of the best attempt.
    """
    check = check or patchcheck.check
    limit = max(1, min(int(max_attempts), MAX_ATTEMPTS))
    attempts: list[dict] = []
    results: list[tuple[dict, dict]] = []           # (patch, check result) per attempt
    calls = 0
    patch = dict(first_patch or {})
    stop = ""
    n = 1
    while True:
        result = check(snapshot, files=patch, spec=spec)
        attempts.append(_row(n, "run" if n == 1 else "retry", patch, result))
        results.append((patch, result))
        if result["status"] == statuses.FIX_VERIFIED:
            stop = f"{statuses.FIX_VERIFIED} on attempt {n}"
            break
        if result["status"] == statuses.FIX_UNVERIFIED:
            stop = (f"attempt {n} could not be verified ({result['reason']}); no retry: the checks cannot run, "
                    "so another proposal could not be checked either")
            break
        if n >= limit:
            break
        calls += 1
        answer = ask(feedback(n, limit, patch, result))
        if not answer.get("ok"):
            stop = f"the model could not answer on attempt {n + 1}: {answer.get('error') or 'no reason given'}"
            break
        new = dict(answer.get("patch") or {})
        if not new:
            stop = f"the model proposed no patch on attempt {n + 1}"
            break
        if patchcheck.sha(new) == patchcheck.sha(patch):
            stop = f"the model repeated the same patch on attempt {n + 1}"
            break
        patch, n = new, n + 1
    at = max(range(len(results)), key=lambda i: (_RANK[results[i][1]["status"]], i))   # the best, the later on a tie
    best_patch, best = results[at]
    if not stop:
        stop = f"{len(attempts)} attempt(s) used; best result {best['status']}"
    return {"status": best["status"], "reason": best["reason"], "patch": best_patch, "patch_check": best,
            "attempts": attempts, "stop_reason": stop, "model_calls": calls}