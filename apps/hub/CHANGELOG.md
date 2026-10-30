# Changelog

All notable changes to VishapHub. Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- **`review`.** Material with a question now means the model reads it and the rules check it
  (before, the question was ignored whenever there was material). The stricter verdict wins,
  the model's findings are marked `source: model`, a rejected key leaves the rules' answer with the
  missing reading named instead of an error, and without any key the run says the question was not put
  to a model. `{"intent": "review"}` is the explicit form.

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
