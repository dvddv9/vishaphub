# Screenshot 2 — Report view (placeholder)

**File to produce:** `02-report.png` · 1280×800 · light theme.

## What must be visible

- The findings table: at least three rows with **ID / CWE / severity / function**.
- One expanded finding showing the explanation text, so the depth is visible.
- The verdict badge (`REQUIRES_REVIEW`).
- The audit-trail strip: `material_hash` (truncated is fine) and `provenance_commit`.

## What must NOT be visible

- Full 64-character hashes running off-screen.
- Any customer material. Use `curl/lib/cookie.c` from the case studies — it is
  public code and already documented.

## Caption for the listing

> Findings carry CWE ids, severity and the function they point at. The report
> ends with the audit trail, so a finding can be traced to an exact commit.
