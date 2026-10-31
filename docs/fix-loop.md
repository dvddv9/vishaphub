# The checking loop

`run_plan(..., fix_loop=True)` (HTTP: `"verify_fix": true` in the body of `/run` and `/run/stream`). Off by
default: it runs the deliverable's tests and the exploit probes, which only happens where the isolation is
confirmed (a worker container, or a network namespace).

1. The model proposes a patch (the run's generator stage). It counts as attempt 1.
2. The hub checks it with the patch check (`docs/patch-check.md`): a bounded diff applied to a copy, the rules
   re-run, the deliverable's own tests and the trusted exploit probes run in the isolation. The model is not
   asked what it thinks of its own patch.
3. `FIX_VERIFIED` ends the loop. `FIX_UNVERIFIED` ends it too: the checks cannot run, so another proposal could not
   be checked either, and the model is not asked again.
4. `FIX_REJECTED` and `FIX_PARTIAL` go back to the model with the concrete reason (for example "the exploit still
   works after the patch: sqli" or "no exploit test for SQL injection: not verified by a test") and the patch it
   was about. At most three attempts in all: at most two more model calls.
5. The same patch twice, no patch, or a model that cannot answer ends the loop with that reason.
6. After three failures the answer is the best status reached (`FIX_PARTIAL` over `FIX_REJECTED`) with the patch
   that earned it. Never a promise of a fix.

## What the model cannot do

- Delete or edit a trusted test, or touch the test configuration: `FIX_REJECTED`, and it is told why.
- Weaken the rules: they are the hub's, not part of any patch.
- Lower the risk verdict: the verdict is merged upward only, and a fix status never changes it (a model that says
  "I fixed it" and "SAFE" leaves the verdict where the rules put it).

## What a result shows

`result.patch` is the patch that was checked and earned the status. `statuses.fix` is its status, with the
reason. `fingerprint.body.evidence.fix_attempts` lists every attempt (number, whether it came from the run or a
retry, the diff hash, the files, the status, the reason) and `evidence.stop_reason` ends with
`fix loop: <why it stopped>` (for example `FIX_VERIFIED on attempt 2`, or `3 attempt(s) used; best result
FIX_PARTIAL`). The fingerprint covers all of it, so another reader can see which patch was checked, what passed
and why the loop stopped.

## Limits

Each retry is a paid model call (the usage meter counts it). The loop needs the exploit targets in a dict spec to
reach `FIX_VERIFIED` for an attack class; without them the best a fix can get is `FIX_PARTIAL`
(`docs/exploit-tests.md`).