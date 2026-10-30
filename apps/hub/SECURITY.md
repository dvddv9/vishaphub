# Security Policy — VishapHub

VishapHub is the one HTTP door in front of the pipeline: it carries a request between the
client, the validator and the analyser, and it keeps the run so a verdict can be opened
again. This file describes what that door protects, and what it does not yet prove.

**Last updated:** 2026-10-30 | **hub 0.4.0**

## What we protect

| Asset | Boundary | Threat |
|---|---|---|
| Material (code, spec, logs, a chat message) | client → hub → model | client code in someone else's report; PII and secrets reaching the provider; prompt injection inside the material |
| Run record | hub → browser | one visitor reading another's run by guessing or listing its id |
| Model key | owner → hub | the key leaving the repository or being spent by a stranger |
| Team data (Postgres) | hub → database | cross-tenant reads, a deleted team's data surviving |

## What is implemented

**Owner on every run.** A run belongs to a token (cookie or the owner header). A request
without one gets `403`; a request for somebody else's run gets `404`, not `403`, so the
existence of that run is not confirmed. `/api/runs`, `/r/<id>`, `/api/runs/<id>` and the
SARIF export all go through the same check.

**Budgets.** Two per-address windows (runs, chat) and two process-wide daily ceilings —
runs at 200 and 5 000 000 characters, chat at 200 and 2 000 000 characters. The chat has
its own ceiling on purpose: a conversation on the site must not spend the run budget.
Exhausted means `429` with `retry-after`, never a thinner answer.

**Redaction before the model.** `proposal._call` sends the material through
`src.tools.redact` (borrowed from the analyser) before it leaves for a provider. Counts by
category come back with the answer. If the analyser is not in the image, nothing is
redacted — the code says so rather than pretending.

**Team mode.** Owners, roles, retention, delete and audit trail in Postgres; quotas per
team, set with `python -m hub.admin set-quota`.

## Known gaps

- **Card numbers are not redacted.** `PII_PATTERNS` in the analyser has email, phone, passport,
  SNILS, IBAN, AWS, Stripe, GitHub, Slack, Google and private keys — no PAN. A card number in
  the material reaches the provider as it is.
- **Row-level security is proven in the analyser, not in the hub.** The hub's team tables rely
  on query-level checks in `teamstore.py`.
- **Runs live in memory** (200 last, until restart) unless the file mirror or Postgres is
  configured. Retention is stated on the report page; there is no per-run delete on the
  in-memory store.
- **The SARIF export depends on the analyser.** Without it the endpoint answers `501`.

## Responsible disclosure

**Do not open a public issue.** Email `dvddv9@users.noreply.github.com` with a description,
steps to reproduce, and what an attacker gains. Do not include live keys or other people's
material. Expect an acknowledgement within a few days; a fix or a stated decision after that.
