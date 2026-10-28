<!-- DRAFT: This document is a technical template. Must be reviewed by a qualified lawyer before publication. -->

# Privacy Policy

**Effective date:** October 18, 2026
**Data controller:** dvddv9 (individual) ("Vishap", "we", "us")
**Contact:** dvddvd9h@outlook.com

This Privacy Policy explains what personal data we collect, why we collect it,
how long we keep it, and the rights you have. It covers the Vishap web
application, API and command-line interface.

## 1. What We Collect

**Account data (via Clerk).** Email address, name (if you provide it), profile
image URL, organisation membership, and authentication metadata. We do not store
passwords — authentication is handled by Clerk.

**Material you submit for analysis.** The code, configuration, specifications,
logs or data you upload or paste, together with the filename you provide. This
material may contain personal data; see Section 3.3.

**Derived analysis data.** The generated report, and an audit trail containing
SHA-256 hashes of the analysed material (`material_hash`, `material_hash_full`),
PII-detection flags, compliance mappings, a provenance record (for example the
git commit analysed), token counts and cost.

**Usage and technical data.** IP address, request paths and timings, HTTP status
codes, job counts and durations, and error diagnostics. Collected through
Prometheus metrics, structured application logs, and OpenTelemetry traces
(exported to Tempo and visualised in Grafana).

**Integration data (GitHub App).** Installation identifiers, repository names,
webhook payloads and the commit references we analyse.

## 2. How We Use Your Data

- **Provide the Service** — run the six-stage analysis pipeline and return the
  report to you.
- **Authenticate and secure your account** — verify identity, enforce access
  control, detect abuse and rate-limit requests.
- **Operate and improve the Service** — measure performance, diagnose failures,
  and understand which features are used.
- **Communicate** — respond to support requests and send service notices. We do
  not send marketing email without consent.
- **Comply with law** — meet legal obligations and respond
  to lawful requests.

**Legal bases (GDPR).** Performance of a contract (Articles 6(1)(b)) for
providing the Service; legitimate interests (6(1)(f)) for security,
abuse prevention and service reliability; consent (6(1)(a)) where we ask for it;
and legal obligation (6(1)(c)) where the law requires us to keep or disclose data.

**Automated decision-making.** The Service produces automated risk assessments of
the material you submit. These assess code and configuration, not individuals, and
do not produce legal effects concerning you. Where a report concerns personal
data, human review remains your responsibility.

## 3. Sub-processors and Third Parties

We share data with the following sub-processors. Each is bound by a data
processing agreement.

| Sub-processor | Purpose | Data shared |
| --- | --- | --- |
| **Clerk** | Authentication and user management | Email, name, profile, session tokens |
| **GitHub** | GitHub App webhooks and repository access | Installation ID, repository name, commit references |
| **LLM: local DSH harness** (runs on the same machine, `HARNESS_URL`) | Generate the analysis report | The analysed material **after PII redaction**, plus the filename — processed on-premise, not transferred to a third party |
| **Grafana Cloud / self-hosted Tempo, Grafana, Prometheus** | Observability: metrics, traces, dashboards | Technical telemetry, job identifiers, endpoint timings |

3.1. **Local LLM (DSH harness).** The only LLM path is a harness running on the
machine Vishap runs on; the analysed material is not sent to a third party. If
`HARNESS_URL` is pointed at a remote host, that host becomes the recipient and this
policy must be updated accordingly.

3.2. **PII redaction.** Personal data detected in the submitted material is
redacted before it is sent to the harness. Redaction reduces risk but is not
guaranteed to be complete — do not rely on it for regulated data.

3.3. **Your responsibility.** If the material you submit contains personal data of
third parties, you are the controller of that data and are responsible for having
a lawful basis. Where that applies, we act as your processor.

3.4. **Legal disclosure.** We may disclose data where required by law, court order,
or to protect the rights, safety and security of our users and the Service.

3.5. **No sale of personal data.** We do not sell personal data and do not share it
for cross-context behavioural advertising.

## 4. Data Retention

| Data category | Retention |
| --- | --- |
| Submitted material (original) | 90 days from submission |
| Generated reports | 90 days from generation |
| Analysis audit trail (hashes, flags) | 12 months |
| Account and profile data | For the life of the account, then 30 days |
| Application logs | 30 days |
| OpenTelemetry traces and metrics | 14 days |
| GitHub App webhook payloads | 30 days |

4.1. Deleted data is removed from primary storage promptly; residual copies may
persist in backups for up to 30 days, after which they are overwritten.

4.2. We may retain data longer where necessary to resolve disputes, enforce
agreements, or comply with law.

## 5. Your Rights (GDPR)

If you are in the European Economic Area, the United Kingdom, or another
jurisdiction with comparable law, you have the right to:

- **Access** — request a copy of the personal data we hold about you.
- **Rectification** — correct inaccurate or incomplete data.
- **Erasure** — request deletion ("right to be forgotten"), subject to legal
  retention obligations.
- **Restriction** — ask us to limit processing while a concern is investigated.
- **Portability** — receive your data in a structured, machine-readable format.
- **Objection** — object to processing based on legitimate interests.
- **Withdraw consent** — at any time, where processing is based on consent.
- **Complain** — lodge a complaint with your local supervisory authority.

5.1. **How to exercise these rights.** Email dvddvd9h@outlook.com from the address
associated with your account. We respond within 30 days and may ask you to verify
your identity.

5.2. **Self-service (planned).** A programmatic endpoint for data export and
deletion — `GET /api/me/data` and `DELETE /api/me/data` — is **not yet
implemented** (TODO). Until it ships, requests are handled manually by email.

5.3. **International transfers.** Some sub-processors operate outside your
jurisdiction. Where personal data leaves the EEA or UK, transfers rely on the
European Commission's Standard Contractual Clauses or an adequacy decision.

## 6. Security

We apply technical and organisational measures appropriate to the risk:

- **Encryption at rest** — sensitive stored values (for example API credentials and
  integration secrets) are encrypted with **Fernet** (AES-128-CBC with HMAC-SHA256
  authentication).
- **Webhook authentication** — inbound GitHub webhooks are verified with
  **HMAC SHA-256 signatures**, with timestamp tolerance to prevent replay.
- **Authentication** — session tokens are signed **JWTs** issued by Clerk and
  validated on every request, with strict key verification.
- **Access control** — API keys and rate limiting protect the analysis endpoints;
  access is scoped to the owning account.
- **Transport** — all client traffic is served over TLS.
- **Audit trail** — SHA-256 hashes make analysed material tamper-evident without
  requiring us to keep the raw content.
- **Observability** — traces, metrics and structured logs support detection and
  response to incidents.

6.1. No system is perfectly secure. If you discover a vulnerability, please report
it responsibly per SECURITY.md rather than disclosing it publicly.

6.2. We notify affected users and relevant authorities of a personal data breach
where the law requires it.

## 7. Cookies

We use a minimal set of cookies and equivalent browser storage.

| Cookie / storage | Provider | Purpose | Type |
| --- | --- | --- | --- |
| `__session`, `__client_uat` | Clerk | Authentication session and session freshness | Strictly necessary |
| `vishap.jobs.v1` (localStorage) | Vishap | Remembers the job IDs your browser submitted, so the dashboard can list them | Functional |

7.1. We do not use advertising or cross-site tracking cookies, and therefore do not
show a consent banner for non-essential cookies. If that changes, we will ask for
consent first.

7.2. You can clear cookies and local storage in your browser at any time. Clearing
the Clerk session cookie signs you out; clearing `vishap.jobs.v1` empties your
dashboard history (the jobs themselves remain accessible via their URLs).

## 8. Contact

- **Data protection contact:** dvddvd9h@outlook.com
- **Support:** dvddvd9h@outlook.com
- **Postal address:** Remote — Yerevan, Armenia
- **EU/UK representative (if applicable):** dvddv9 — Remote — Yerevan, Armenia

If you are not satisfied with our response, you may complain to your local
supervisory authority.
