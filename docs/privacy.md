# Privacy: what is processed where

Measured on 2026-10-31 against the code in this repository. Where something was not checked, it says so.

## 1. Local processing (no data leaves the hub's own process or container)

- The analyser's static rules (`analyse_static`): a function over the text, no model, no network.
- The validator runs the deliverable's tests only where a network namespace or a worker container confirms
  isolation (`docker run --network none --read-only`). If isolation cannot be confirmed, nothing is run. The
  report records which isolation held. The worker starts without credentials and refuses to run if it finds
  credential-looking environment variable names.
- No submitted code is sent to a hosted sandbox; hosted code execution is not enabled.

## 2. Model provider (Anthropic API)

When a run, review or chat uses a model, the text the client supplied goes to the provider only after
redaction: material, spec, question, chat message and chat history (`hub/privacy.py`, using the analyser's
`src.tools.redact`). Provider error text is also redacted and cut before it is returned or logged.

- Secrets are removed by pattern (values only).
- Card numbers are removed when they pass the Luhn checksum. Long numbers that do not pass it, such as order
  numbers and timestamps, remain unchanged.
- If the redaction code is unavailable, the request is refused and nothing is sent.

Rules enforced and tested in `apps/hub/tests/test_privacy_paths.py`:

- every client-controlled text is redacted before it is put in a provider request, not only the material;
- redaction happens before the length limit, so a truncated value is not left half-visible;
- if redaction is unavailable, nothing is sent;
- provider error text is redacted before return or logging.

Not covered: redaction is pattern-based. Names, addresses and free-text personal data are not redacted; an
unknown secret format can reach the provider.

## 3. Data map: storage, access and retention

| Data | Where it is handled or stored | Access and retention |
|---|---|---|
| Submitted material, spec, questions and chat | Hub process; if a model is used, redacted text is sent to Anthropic. Submitted tests run only in confirmed local isolation. | Anonymous run reports are kept in process memory (last 200 by default); an optional file mirror is controlled by `VISHAP_HUB_RUNS_FILE`. |
| Run report | Verdict, steps, findings, summary, proposed patch and input fingerprint. Findings or patches can contain code derived from the submission. | Anonymous reports are opened with the run's owner token. Team reports are in Postgres and expire after 30 days by default, or the team's configured retention; expired reports are unreadable before the purge runs. |
| Team identity and credentials | Team keys are hashed; the model key supplied by a client is not stored. | The hub server uses `vishap_hub_app`, a `NOSUPERUSER NOBYPASSRLS` role. It has no direct read access to `teams`, `users` or `api_keys`; authentication uses a restricted database function. |
| Team audit and usage records | Postgres in team mode. Audit rows record actor, key, address, target and outcome, without the run content. Usage rows contain request sizes and token counts. | Row-level security scopes `runs`, `audit_log` and `usage` to the active team. The app role can append audit rows but cannot update or delete them. Audit rows have no automatic expiry; deleting a run leaves its audit record and an unlinked usage record. |

The anonymous file mirror persists across restarts and is capped by the run store's retention behavior; deleting its
file removes the mirror. Anonymous in-memory reports disappear on restart and have no per-run delete. In team mode,
users can read runs within their team; members can delete their own, and owners can delete any team run. The RLS
policies and the application query filters are tested separately against a real Postgres role in
`apps/hub/tests/test_teams.py`; CI supplies Postgres and fails if those tests are skipped.

## 4. Reports, fingerprints and logs

For a material containing a card number, the run report, fingerprint and captured log output held no card number
in the tested paths. The fingerprint hashes the material the client sent, not the redacted text the model saw.
The report may contain findings that quote source lines and a patch derived from the source. Other stored or
logged content has not been audited here.

## 5. External code executors (not enabled)

No submitted code is sent to a hosted sandbox. This stays so until all of: a data-processing agreement, explicit
contract text about passing sources, tests and spec to the provider, a dedicated workspace with a minimal key, a
successful run on synthetic code, and confirmed deletion with a deny-all policy. A synthetic probe of one
provider's sandbox was run on 2026-10-31; no client code was involved.
