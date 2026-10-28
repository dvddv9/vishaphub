# Compliance readiness

Where Vishap stands against the frameworks enterprise buyers ask about. This is
a **self-assessment, not an audit** — nothing here has been certified, and the
status markers are our own honest reading of what exists today.

| Framework | Typical timeline | Status | What is missing |
| --- | --- | --- | --- |
| **SOC 2 Type I** | 6–12 months | Not started | Policies, auditor, evidence collection over a period |
| **SOC 2 Type II** | +3–12 months after Type I | Not started | An observation window with controls actually running |
| **ISO 27001** | 6–12 months | Not started | ISMS, risk register, management review, certification body |
| **HIPAA** | 3–6 months | Not applicable yet | Required only if handling PHI; needs a BAA and a security officer |
| **Penetration test** | 2–4 weeks | Not started | Scope agreement and an external tester |

## What is genuinely in place

These are implemented controls, not intentions — and they are the ones that make
the audit conversation shorter:

- **Tenant isolation enforced by the database.** PostgreSQL row-level security
  with `FORCE`, so the table owner is subject to the policy too.
- **Access control.** Clerk-issued JWTs verified on every request, per-tenant
  scoping, API-key protection and rate limiting on analysis endpoints.
- **Audit trail.** Every report carries a SHA-256 hash of the analysed slice and
  a provenance commit; the trail is exportable as CSV or JSON.
- **Observability.** Prometheus metrics and OpenTelemetry traces across the
  pipeline, with Grafana dashboards.
- **Data subject rights.** Export and erasure endpoints (`GET /api/me/data`,
  `DELETE /api/me`), plus a written retention policy.
- **Encryption.** TLS in transit; Fernet for stored secrets; HMAC-verified
  webhooks.
- **Legal documents.** Terms, Privacy Policy and DPA templates are written
  and in the repository.

## Documents

| Document | Purpose |
| --- | --- |
| [`SOC2-checklist.md`](SOC2-checklist.md) | Trust Services Criteria, criterion by criterion, with current status |
| [`pentest-template.md`](pentest-template.md) | Scope, methodology, timeline and deliverables for an external test |

## Suggested order

1. **Penetration test first** (2–4 weeks). It is cheap relative to an audit, it
   finds real issues, and its report becomes evidence you can show a SOC 2
   auditor later.
2. **Write the policies** while the test runs: access control, change
   management, incident response, vendor management, business continuity.
   Templates from Vanta or Drata cover most of it.
3. **Pick a compliance platform** (Vanta, Drata, Secureframe). They automate
   evidence collection from AWS/GitHub/Clerk; doing this by hand for a year is
   not worth the savings.
4. **SOC 2 Type I**, then run controls for the observation window before Type II.
5. **ISO 27001** only if a specific customer requires it — it overlaps heavily
   with SOC 2 and roughly doubles the policy work.

## Honest caveats

- Retention windows (90 days for material, 14 days for traces) are stated in the
  Privacy Policy; confirm the storage layer enforces them before claiming it in
  an audit.
- No EU/UK representative has been appointed, which GDPR Article 27 may require.
- SSO (SAML) returns `501` until the Clerk Enterprise tier is enabled, so an
  enterprise buyer asking for SSO today will be told "not yet".
