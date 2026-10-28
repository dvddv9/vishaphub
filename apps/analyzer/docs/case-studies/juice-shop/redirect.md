# Juice Shop redirect.ts — Open redirect + invisible guard
**File:** routes/redirect.ts (~35 LOC) | **Level:** D2 | **Cost:** ~$0.007
## Found
**CRITICAL: Open redirect** — all protection relies on invisible `isRedirectAllowed`. If it uses `startsWith` without normalization > bypass via `trusted.com.evil.com`, `trusted.com@evil.com`.
**CRITICAL: Policy desync** — `isRedirectAllowed` ? `isUnintendedRedirect`.
**IMPORTANT:** `query.to as string` masks runtime type. Race on shared `challenges`.
