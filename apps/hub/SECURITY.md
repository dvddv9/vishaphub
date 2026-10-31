# Security Policy — VishapHub

VishapHub is the HTTP entry point for the generator, validator and analyser. This policy describes the data
paths and controls present in the repository; deployment-specific settings still need to be checked on the live
service.

**Last updated:** 2026-10-31 | **hub 0.5.0**

## Data map

| Data | Processing path | Storage / exposure |
|---|---|---|
| Submitted material, spec, question, chat message and chat history | Handled by the hub. Static rules run locally. If a model is used, client text is redacted before it is sent to the Anthropic API. | A run report can contain findings that quote source lines, the model's summary and a proposed patch derived from the source. |
| Submitted tests and entry point | Run only when network isolation is confirmed: a network namespace or a worker container with `--network none` and a read-only root. | No submitted code is sent to a hosted sandbox; hosted code execution is not enabled. |
| Run report and fingerprint | Built by the hub after the checks. The fingerprint hashes the original input, not the redacted text sent to a model. | Anonymous mode keeps up to 200 runs in process memory; an optional file mirror is controlled by `VISHAP_HUB_RUNS_FILE`. Team mode stores runs in Postgres for 30 days by default, or the team's configured retention. |
| Team audit and usage metadata | Written in Postgres for signed-in team actions. Audit entries contain actor, key, address, target and outcome, not run content. Usage rows contain sizes and token counts. | Audit rows have no automatic expiry. Deleting a team run leaves its audit row and an unlinked usage row. |
| Credentials | A client's model key is used for the provider call and is not stored. Team API keys are stored as SHA-256 hashes; anonymous owner tokens are also stored as hashes. | The server role cannot directly read `teams`, `users` or `api_keys`; authentication goes through a restricted database function. |

## Controls in the code

**Redaction before the provider.** When a model is called, material, spec, question, chat messages and chat history
are redacted before the request is made. Secrets are removed by pattern; card numbers are removed when they pass
the Luhn checksum. Provider error text is redacted and cut before it is returned or logged. If the redaction code
is unavailable, the hub sends nothing. This is pattern-based: names, addresses and free-text personal data are
not redacted, and an unknown secret format can reach the provider. The paths are covered by
`apps/hub/tests/test_privacy_paths.py`.

**Run access.** Anonymous reports require the owner's token; the stored token is a hash. These are not accounts:
clearing the cookie loses access. Identical submissions can receive the same run id and share access to that
report, and the demonstration run is public by design, as described in the root README. Team users can read runs in their team; members can delete their own,
and owners can delete any team run.

**Team isolation.** Application queries filter by team, and Postgres row-level security independently scopes
`runs`, `audit_log` and `usage` to the active team. The server connects as `vishap_hub_app`, a `NOSUPERUSER NOBYPASSRLS` role. It cannot read `teams`, `users` or `api_keys` directly and has only `SELECT`/`INSERT` access
to audit rows, so it cannot update or delete them. `apps/hub/tests/test_teams.py` builds a scratch Postgres
database and tests the app role and database policies separately. CI supplies Postgres and fails if team tests
are skipped.

**Validator isolation.** Submitted tests receive a clean environment. A public endpoint requiring strict isolation
refuses to run code unless a network namespace or worker container confirms the boundary. The worker runs without
credentials. A Python socket guard is reported as `guard`, not mistaken for process-level network isolation.

**Storage and deletion.** Anonymous in-memory runs disappear on restart; the optional file mirror persists until
its retained entries are displaced or the file is deleted. Team runs are unreadable as soon as their configured
retention expires, then removed by the purge. An owner can delete a team run; its audit metadata remains. The
anonymous browser mode has no per-run delete. Audit records have no automatic expiry yet.

**Budgets and proxy addresses.** Anonymous and team requests have limits. For anonymous per-address limits and
the IP in the audit trail, Render must pass the trusted proxy header and the correct number of trusted hops must
be configured. The hub uses entries counted from the right of the header, not the client-controlled left side.

## Observability gap: address selected by the live service

The Render service has `VISHAP_HUB_TRUST_HEADER=x-forwarded-for` and `VISHAP_HUB_TRUSTED_HOPS=1`. The repository
has not recorded the address the running process actually selects. If the header is missing, unparsable or not
picked up, callers share the proxy's socket-address bucket instead of separate anonymous buckets. A behavioral
probe cannot distinguish these cases. Check `address_used`, `trust_header` and `trusted_hops` at
`GET /api/team/diagnostics` with an owner key, or inspect a service log that records the selected address, before
claiming per-visitor limits publicly.

## Known gaps

- Redaction does not cover names, addresses, free-text personal data or secret formats the patterns do not know.
- The anonymous browser mode has no per-run delete; identical submissions can share a run id.
- Audit records have no automatic expiry or growth cap.
- The analyzer's `SAFE` verdict is limited to measured rule coverage; it is not proof that code has no flaws. See
  the root README for the current coverage and limits.

## Responsible disclosure

**Do not open a public issue.** Email `dvddv9@users.noreply.github.com` with a description, steps to reproduce,
and what an attacker gains. Do not include live keys or other people's material. Expect an acknowledgement within
a few days; a fix or a stated decision after that.
