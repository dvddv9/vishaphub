# CI contract, exports and re-checks

Stable for pipelines. The contract is versioned: `schema` is `vishap.run/1`. Fields may be added; a field is
never removed or changed in meaning without a new schema.

## Running from a pipeline

CLI: `vishap-hub run --intent analyse --material app.py --fail-on fail --require-complete`.
HTTP: `POST /run` (or `/run/stream`) with `"fail_on"` and `"require_complete"` in the body.

| Option | Meaning |
|---|---|
| `fail_on` = `review` / `fail` / `emergency` | the lowest verdict that fails the check. Default `fail`. The hub does not issue SAFE yet, so a rules-only run usually ends at `REQUIRES_REVIEW`: with the default it passes, with `review` it fails. |
| `require_complete` | a run whose verification is not `COMPLETE` does not pass, whatever its verdict says. A run that checked nothing, or only part of its plan, must not be a green build. |

Exit codes (CLI), and `ci.exit_code` (HTTP):

| Code | Meaning |
|---|---|
| 0 | pass |
| 1 | the verdict is at or above `fail_on`, or the run did not pass its own gates (an unreadable verdict fails too) |
| 2 | bad usage (the CLI's own, for example a missing file) |
| 3 | the verdict is fine but the checking was incomplete (only with `require_complete`) |

A failing verdict wins over incompleteness. The response carries a `ci` block next to the run:

```json
{"schema": "vishap.run/1", "pass": false, "exit_code": 3, "fail_on": "fail", "require_complete": true,
 "verdict": "REQUIRES_REVIEW", "fix": "NO_PATCH", "verification": "PARTIAL", "complete": false,
 "reasons": ["the checking was PARTIAL: ran analyser; not run validator"]}
```

`ci` belongs to the request, not to the run: it is computed per call and never stored with the run. A bad
`fail_on` is a 400 and nothing is run. `complete` is in the block even when `require_complete` is off, so a
script can see an incomplete green.

## Reading a run back

| Path | What |
|---|---|
| `GET /api/runs` | the runs you may see, newest first; each row carries `fix` and `verification`, and the runs page marks a run that was not fully checked |
| `GET /api/runs/<id>.json` | the stored run, with its fingerprint |
| `GET /api/runs/<id>.sarif` | SARIF for code scanning |
| `GET /api/runs/<id>.md` | Markdown: the verdict and the three results, findings, what was not checked, the evidence and whether the record is intact. Never the material or the files: the hub does not keep them |
| `GET /api/verify/<id>` | re-check the record: the digest is recomputed from the body |
| `POST /api/verify/<id>` with `{"files": {path: text}}` | also check that these are the files the record names (their hashes) |
| `DELETE /api/runs/<id>` (teams) | the run row goes with its result and patch; the audit row stays (who, when, which id, no content) |

All of them are as private as the run: another owner, or a stranger, gets the same 404 as for a run that never
existed.

## Retention, limits, audit (teams)

Retention days per team, quotas per minute and per day, and the audit trail (`GET /api/team/audit`, owners only)
are the team mode's (`VISHAP_HUB_DATABASE_URL`). An expired run is not returned and is purged on a schedule.

## Comparing and deleting, on the pages

- `/compare?a=<id>&b=<id>` is the page for the same comparison; the report page has a form for it.
- `/r/<id>/delete` asks first, in words: what goes, what does not, and that it cannot be undone. Looking at that page
  deletes nothing; the button is a POST, and a POST that comes from another site is refused.
- **Team:** the run row goes with its result, findings and patch. The audit row stays (who, when, the run id, no content).
  Usage counters keep their numbers and let go of the id. An owner may delete any run; a member only their own; a viewer none.
- **Visitor:** the run and the claim on it go. Two visitors who run exactly the same material share one record and both
  own it: removing yours takes the run out of your reach, and the record itself goes when nobody owns it. The page's own
  example cannot be deleted.
- Not covered: copies made outside the hub (an exported file, a link someone saved). Running the same material again
  makes a new run with the same id.
