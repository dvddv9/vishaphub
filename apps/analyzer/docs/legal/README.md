<!-- DRAFT: This document is a technical template. Must be reviewed by a qualified lawyer before publication. -->

# Legal Documents

- [Terms of Service](./TERMS.md)
- [Privacy Policy](./PRIVACY.md)
- [Data Processing Agreement (DPA)](./DPA.md)

⚠️ **These are technical templates.** Must be reviewed by a lawyer before publication.

## What is here

| File | Purpose |
| --- | --- |
| [`TERMS.md`](./TERMS.md) | Terms of Service — 11 sections. |
| [`PRIVACY.md`](./PRIVACY.md) | Privacy Policy — 8 sections, GDPR-oriented, documents sub-processors and retention. |
| [`DPA.md`](./DPA.md) | Data Processing Agreement — 10 sections, GDPR Article 28 processor terms, sub-processor table, SCCs, audit rights. Only needed if someone processes personal data through the Service on your behalf. |

## How to use these templates

1. **Replace the placeholders.** Search for `[` in every file:

   | Placeholder | Replace with |
   | --- | --- |
   | `[Effective Date]` | Date the documents go live |
   | `[Company Legal Name]` | Registered legal entity name |
   | `[Customer Legal Name]` | Counterparty name (DPA) |
   | `[Your Country]` | Jurisdiction governing the Terms |
   | `[Company Postal Address]` | Registered address |
   | `[Representative Name and Address]` | EU/UK representative, if required |
   | `support@vishap.dev` | Real support address |
   | `privacy@vishap.dev` | Real privacy/DPO address |

2. **Verify the factual claims.** Sections that describe the implementation — Fernet
   encryption, HMAC webhook verification, JWT sessions, PII redaction, row-level
   security, audit-trail hashes, observability stack, retention windows, the
   `GET /health` probe — must match what actually ships. Re-read them after any
   change to the pipeline or infrastructure.

3. **Get legal review.** These are engineering drafts, not legal advice. A qualified
   lawyer in your jurisdiction must review them before publication.

4. **Publish.** Copy all three files into `docs-site/docs/legal/` as `terms.md`,
   `privacy.md` and `dpa.md` (the Docusaurus mirrors), register them in
   `docs-site/sidebars.ts` under the `Legal` category, and link them from the
   landing page footer.

## Known gaps (TODO before launch)

- `GET /api/me/data` and `DELETE /api/me/delete` — self-service export/deletion
  endpoints referenced by the Privacy Policy and the DPA are **not implemented yet**.
- Governing law and jurisdiction are placeholders — must be chosen deliberately.
- No EU/UK representative has been appointed, although the DPA refers to SCCs.
- The DPA describes sub-processor locations (US/CN/EU) that must be confirmed
  against where the deployment actually sends data.
- The 90-day material retention window and the 14-day trace retention are policy
  statements; confirm the storage layer actually enforces them.
- The DPA is not linked from the landing page footer — only Terms and Privacy
  are.

## Mirrors

`docs/legal/` is the editable source. `docs-site/docs/legal/` holds the copies that
Docusaurus renders at `/docs/legal/terms`, `/docs/legal/privacy`,
and `/docs/legal/dpa`. They differ only in relative link targets
(`./PRIVACY.md` vs `./privacy`), so **edit both** — or delete the mirror and
generate it if the duplication becomes a burden.
