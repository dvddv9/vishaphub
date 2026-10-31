# Verdicts and statuses

A run gives three results. They answer different questions and are never merged into one.

| Result | Question | Where |
|---|---|---|
| **risk verdict** | How risky is the material? | `verdict`, `statuses.risk` |
| **fix status** | What is known about a proposed fix? | `statuses.fix` |
| **verification status** | How much of the planned checking really ran, and where? | `statuses.verification` |

The API (`/run`, `/run/stream`, `/api/runs`), the report page (`/r/<id>`) and the interface show the same
three, with the same words. Runs stored before the statuses existed show no "Three results" block.

## Risk verdict

Ranked in `hub/verdicts.py`. The strictest wins. What stands behind it is named in `statuses.risk.basis`:

- **rules**: the analyser's static rules read the material. A pattern match, not a six-stage analysis.
- **tests**: the validator ran the deliverable's own tests in an isolated environment.
- **model**: a recommendation. It is merged last and only upwards: it can raise a verdict, never lower it.
  When nothing but the model stands behind a verdict, `rests_on_model_alone` is true and the report says
  "a guess".

| Verdict | Meaning |
|---|---|
| SAFE / PASS | the rules found nothing / the tests passed. Not a promise; the hub does not issue SAFE yet |
| NEEDS_REVIEW / REQUIRES_REVIEW | a person should read the findings |
| FAIL | a broken promise: a check failed |
| EMERGENCY | a security signal; it is never hidden by a failing test |
| ERROR | the run could not answer; never a pass |

## Fix status

A fix status complements the risk verdict and never softens it: a verified fix does not turn FAIL into PASS.

| Status | Meaning |
|---|---|
| NO_PATCH | no patch was proposed |
| FIX_UNVERIFIED | a patch was proposed by the model; it was not applied to a snapshot and re-checked |
| FIX_VERIFIED | applied to a copy, the mandatory checks passed (not merely: the finding disappeared) |
| FIX_PARTIAL | some mandatory checks passed, some did not |
| FIX_REJECTED | the patch failed, left its allowed paths, or touched trusted checks |

A run produces NO_PATCH or FIX_UNVERIFIED by default. The other three come from the patch check
(`hub/patchcheck.py`, see `docs/patch-check.md`), which a run asks for with `check_patch=True` and which
`vishap-hub patch-check` runs on its own. An unknown status is refused, not shown.

## Verification status

| Status | Meaning |
|---|---|
| COMPLETE | every planned checking stage ran and nothing is listed as not checked |
| PARTIAL | some planned stage did not run, or the plan itself is partial, or something is listed as not checked |
| NOT_RUN | no checking stage ran |
| ERROR | the run failed before any check produced a result |

`statuses.verification.isolation` names the isolation the validator ran under (kind, image, container,
whether the cleanup was confirmed), when it ran in a worker container.
## Evidence and integrity

The run's fingerprint (`fingerprint.body.evidence`) carries what a claim rests on, and the digest covers it:

- the snapshot the client sent (file hashes), the model's patch (diff hash and file hashes);
- what the validator actually ran on: the client's own files, or the model's patch when the client sent
  none (`validator_ran_on`), and what the analyser read. A model patch is otherwise only read by the
  rules, which is why a proposed fix stays `FIX_UNVERIFIED`;
- the versions of the rules and the sandbox profile (`worker-v1` flags and caps, with a hash);
- every check that ran, with its result, and what was left unverified;
- the number of attempts and why they stopped;
- whether the temporary environment's cleanup was confirmed (`null` when no container was used).

Nothing in it is random: no time, no container name. The same run gives the same bytes.
`fingerprint.verify(fp, files)` recomputes the digest and, given the files, their hashes; the report page
shows "record intact" or "record NOT intact" for the stored record.