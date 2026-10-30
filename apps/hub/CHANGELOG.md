# Changelog

All notable changes to VishapHub. Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Security

- **A silent or malformed connection can no longer hold the hub's threads.** A read timeout (30 s, `VISHAP_HUB_READ_TIMEOUT`), a ceiling on runs in flight (4, `VISHAP_HUB_MAX_CONCURRENT_RUNS`; the 5th is a `503` before it spends any budget), and a `Content-Length` that is not a number is a `400` instead of a dropped connection (`/run`, `/chat`, `/speak`, `/login`).
- **A run that raises is a `500` that says so, not a dead socket, and neither `/run` nor `/run/stream` hands the exception text to the client** (it goes to the log).
- **`render.yaml` sets `VISHAP_HUB_TRUST_HEADER=x-forwarded-for` and `VISHAP_HUB_TRUSTED_HOPS=1`**, so the per-address limits are per visitor behind Render's proxy and not one bucket for everyone. Check it with `GET /api/team/diagnostics`.
- **Validator 0.3.0: the visitor's tests no longer see the hub's environment.** The hub runs a deliverable's own tests and imports its entry point inside the service process; those subprocesses used to inherit every variable of the host (model key, database URLs). They now get `PATH`, temp dirs and locale only. A spec path that is absolute, climbs with `..` or an entry that is not a dotted module name is refused (`FAIL`, nothing run) - a test file outside the deliverable used to be executed. Pytest exiting 0 with every test skipped is no longer a green run; `todos`/`stubborn` in code are no longer `stub` markers. Not a sandbox: the code under test can still reach the network.

### Changed

- **Run page and report.** The rules' findings about the model's own patch sit in their own block (their line numbers refer to the patch); the model's summary is labelled as the model's, with a note that the hub did not run its patch; a second route the rules flag without authentication says which model finding may already cover it (`possibly_covered_by`; nothing is dropped).

### Added

- **`review`.** Material with a question now means the model reads it and the rules check it
  (before, the question was ignored whenever there was material). The stricter verdict wins,
  the model's findings are marked `source: model`, a rejected key leaves the rules' answer with the
  missing reading named instead of an error, and without any key the run says the question was not put
  to a model. `{"intent": "review"}` is the explicit form.
- **Findings from two readers are joined.** A model finding and a rules finding for the same class of
  defect near the same line are one finding with `seen_by`; `agreement` counts what each reader found
  alone and what both did. The report page and the main page show it, with the rules' fix.

### Fixed

- The rules' findings had an empty `message` (the scan calls it `title`); they now carry `message`,
  `cwe` and `fix`.
- A `REQUIRES_REVIEW` verdict carried the definition of `SAFE` as its `meaning`; it now says what
  REQUIRES_REVIEW means for that run (the rules found something / they cannot vouch for this text).

## [0.4.0] — 2026-10-30

### Added

- **Team mode.** Owners, roles, per-team retention, delete and an audit trail; runs and teams
  in Postgres, isolation covered by tests. Admin entry point: `python -m hub.admin`.
- **Spend control.** Per-team and per-user quotas; a process-wide budget for runs and
  characters that survives restarts; alerts on threshold; measured tokens kept apart from
  estimates (`meter.py`).
- **A budget of its own for the chat.** Anonymous messages that reach a model spend
  `VISHAP_HUB_GLOBAL_CHATS_PER_DAY` / `VISHAP_HUB_GLOBAL_CHAT_CHARS_PER_DAY`, not the run
  budget: a conversation on the site cannot close the door for runs.
- **SARIF export.** `GET /api/runs/<id>.sarif` returns SARIF 2.1.0, written by the analyser's
  own writer. Owner check identical to the report itself; `501` when the analyser is absent.
- **Redaction before the model.** `proposal._call` passes the material through
  `src.tools.redact` before it leaves; counts by category come back in the result.

### Security

- **Owner on every run.** Without a token `403`; for someone else's run `404`, so existence is
  not confirmed. `/api/runs`, `/r/<id>`, `/api/runs/<id>` and the SARIF export share the check.
- `API_KEY_PEPPER` in the analyser is refused at startup when it is still a placeholder and
  tenant keys are on.

### Known gaps

- Card numbers are not redacted (no PAN pattern).
- Runs live in memory (200 last, until restart) unless the file mirror or Postgres is set.
- Row-level security is proven in the analyser, not in the hub.
