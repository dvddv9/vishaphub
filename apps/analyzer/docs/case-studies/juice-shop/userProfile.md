# Juice Shop userProfile.ts — RCE (eval)
**File:** routes/userProfile.ts (~90 LOC) | **Level:** D3 | **Cost:** ~$0.007
## Found
**CRITICAL: RCE** — `eval(code)` on user-controlled `username` from DB. Remote code execution in Node.js process.
**CRITICAL: CSP bypass** — `profileImage` interpolated into `script-src`.
**CRITICAL:** `unsafe-eval` in CSP. Challenge-flag activates eval path.
**IMPORTANT:** Backslash-prefix `'\\' + username` is NOT escaping. `eslint-disable-line no-eval` hides the problem.
## Fix
Remove eval. Remove `unsafe-eval`. Allowlist + nonce for CSP. Disable challenge at build time.
