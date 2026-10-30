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

Today only NO_PATCH and FIX_UNVERIFIED are produced. The other three are reserved for the patch check
(`statuses.fix` accepts them; an unknown status is refused, not shown).

## Verification status

| Status | Meaning |
|---|---|
| COMPLETE | every planned checking stage ran and nothing is listed as not checked |
| PARTIAL | some planned stage did not run, or the plan itself is partial, or something is listed as not checked |
| NOT_RUN | no checking stage ran |
| ERROR | the run failed before any check produced a result |

`statuses.verification.isolation` names the isolation the validator ran under (kind, image, container,
whether the cleanup was confirmed), when it ran in a worker container.