# SOC 2 readiness checklist

Self-assessment against the AICPA Trust Services Criteria (TSC). **This is not an
audit and does not certify anything.** Status markers reflect what exists in the
repository today, not what a report would say.

Legend: ✅ implemented · ⏳ partial / needs documentation · ❌ not started

## Common Criteria (Security)

Security is the only category required for a SOC 2 report; the others are added
when a customer asks for them.

| Criterion | What an auditor expects | Status | Evidence / gap |
| --- | --- | --- | --- |
| **CC1** Control Environment | Written policies, defined roles, code of conduct, org chart | ⏳ | No policies exist yet. The repository is the only documented process. |
| **CC2** Communication & Information | Internal communication of objectives; external commitments documented | ⏳ | Terms, Privacy and DPA are written. No internal comms or training record. |
| **CC3** Risk Assessment | Risk register, annual assessment, fraud risk considered | ❌ | Nothing formal. Needs a register with owners and review dates. |
| **CC4** Monitoring Activities | Ongoing monitoring of controls, not just systems | ⏳ | Prometheus and OpenTelemetry cover the system, not the controls. No control testing schedule. |
| **CC5** Control Activities | Documented controls mapped to risks; segregation of duties | ⏳ | Technical controls exist (see CC6–CC8) but are not mapped to risks on paper. |
| **CC6** Logical & Physical Access | Identity lifecycle, least privilege, MFA, access reviews, deprovisioning | ✅ | Clerk-issued JWTs verified per request; PostgreSQL RLS with FORCE; API keys + rate limiting. Physical access inherited from the cloud provider. Gap: no scheduled access review record. |
| **CC7** System Operations | Monitoring, incident detection and response, capacity management | ✅ | Prometheus metrics, OpenTelemetry traces, Grafana dashboards, structured logs. Gap: incident response runbook is not written down. |
| **CC8** Change Management | Documented change process, review, testing, approval | ⏳ | Git history, PR review and CI exist. No written change-management policy or approval record beyond the PR itself. |
| **CC9** Risk Mitigation | Vendor risk management, business continuity, insurance | ⏳ | Sub-processors are listed in the DPA with locations. No vendor assessments, no BCP/DR document, no insurance. |

## Availability (A1)

| Criterion | What an auditor expects | Status | Evidence / gap |
| --- | --- | --- | --- |
| **A1.1** Capacity | Capacity monitored and planned | ⏳ | Metrics exist; no documented capacity plan or thresholds. |
| **A1.2** Recovery | Backups, restore testing, DR objectives (RTO/RPO) | ❌ | No backup/restore procedure or test record. |
| **A1.3** Availability commitment | Availability commitment documented and measured | ⏳ | No SLA is published: the service is free and best-effort. Uptime is not measured automatically yet. |

## Processing Integrity (PI1)

| Criterion | What an auditor expects | Status | Evidence / gap |
| --- | --- | --- | --- |
| **PI1** | Inputs validated, processing monitored, outputs verified, errors corrected | ⏳ | Deterministic SAST/SCA tools fail open; every report carries a SHA-256 of the analysed slice and a provenance commit. Gap: no formal validation procedure and no error-correction workflow. |

## Confidentiality (C1)

| Criterion | What an auditor expects | Status | Evidence / gap |
| --- | --- | --- | --- |
| **C1.1** | Data classified; confidentiality commitments documented | ⏳ | Encryption: TLS in transit, Fernet for stored secrets. Tenant isolation enforced by RLS. Gap: no data classification scheme. |
| **C1.2** | Disposal of confidential data | ✅ | `DELETE /api/me` erases jobs and history per tenant; retention windows are stated in the Privacy Policy. Gap: confirm the storage layer actually enforces the 90-day window. |

## Privacy (P1–P8)

| Criterion | Status | Notes |
| --- | --- | --- |
| **P1** Notice and communication | ⏳ | Privacy Policy published; no versioning or change-notification process. |
| **P2** Choice and consent | ❌ | No consent management; not required today because there is no marketing email. |
| **P3** Collection | ✅ | Collection is limited to what the service needs, and PII is redacted before any model call. |
| **P4** Use, retention, disposal | ⏳ | Retention windows documented (90 days material, 12 months audit trail, 14 days traces); enforcement not verified. |
| **P5** Access | ✅ | `GET /api/me/data` exports every record for the tenant. |
| **P6** Disclosure to third parties | ✅ | Sub-processors and their locations are listed in the DPA; there is no sale or ad-sharing of data. |
| **P7** Quality | ⏳ | Users can correct account data through Clerk; no dispute process documented. |
| **P8** Monitoring and enforcement | ❌ | No privacy programme owner, no complaint handling procedure. |

## What to do next

Ordered by cost-effectiveness, not by criterion number:

1. **Write the policies.** Access control, change management, incident response,
   vendor management, business continuity, data classification, acceptable use.
   This unblocks CC1, CC2, CC5, CC9 and most of the ⏳ rows. Most of the content
   already exists as practice — it needs to be written down.
2. **Pick a compliance platform** (Vanta, Drata, Secureframe). They integrate
   with GitHub, cloud and Clerk, and automate evidence collection for CC6–CC8.
   Hand-collecting evidence for a year costs more than the subscription.
3. **Define RTO/RPO and test a restore.** A1.2 is currently a hard ❌ and is the
   easiest to fail in an audit because there is no artifact at all.
4. **Start measuring uptime** before making any availability promise. A commitment
   nobody measures is a liability, not a selling point.
5. **Engage the auditor** once policies exist and controls have run for at least
   three months. SOC 2 Type I first; Type II needs an observation window.

Realistic timeline: **3–6 months of preparation**, then the observation period
for Type II. Budget is dominated by the platform subscription and the auditor,
not by engineering time.

## Explicitly not claimed

- No SOC 2 report, no ISO 27001 certificate, no HIPAA BAA.
- No external penetration test has been performed.
- No EU/UK representative has been appointed (GDPR Article 27 may require one).
- SSO (SAML) returns `501` until the Clerk Enterprise tier is enabled.
