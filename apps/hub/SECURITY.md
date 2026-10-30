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

## Observability gap: which address the app actually uses

`VISHAP_HUB_TRUST_HEADER=x-forwarded-for` and `VISHAP_HUB_TRUSTED_HOPS=1` are set on the Render
service, and the deployment carrying them is live. What we have **not seen** is the address the
application actually selects from that header. This is a gap in observation, not a known
misconfiguration — the variables are in place, the result of reading them is not recorded anywhere
we can read.

**Why it matters.** The same request path gives two different services:

- header read and parsed → the limiter key is the visitor's address, each visitor has a bucket;
- header absent, unparsable, or the variable not picked up by the process → the key is the socket
  address, which behind Render is the proxy. Every visitor then shares one bucket, and "20 a
  minute per address" means 20 a minute for the whole site: one visitor closes the door for
  everyone.

From outside both look the same — the door closes either way, but one variant closes it too wide.
Behavioural probes cannot tell them apart: a forged left-most `X-Forwarded-For` entry changes
nothing in either variant.

**How to close it.** One of these, and then say which:

- connect Postgres, issue an owner key, and read `GET /api/team/diagnostics` — it returns
  `socket_address`, `address_used`, `trust_header`, `trusted_hops` and every forwarded header
  received; `address_used` is the answer;
- find a service log line that records the chosen address per request.

Until one of those exists, do not claim per-visitor limits in public.

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
