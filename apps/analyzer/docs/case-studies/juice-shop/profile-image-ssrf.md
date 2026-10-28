\# Juice Shop profileImageUrlUpload.ts — SSRF + stored XSS



\*\*File:\*\* routes/profileImageUrlUpload.ts (\~50 LOC)

\*\*Level:\*\* D2

\*\*Cost:\*\* \~$0.007

\*\*Time:\*\* \~60 sec



\## Found



\### 1. SSRF (CRITICAL)



`fetch(url)` with user-controlled `req.body.imageUrl` — no allowlist,

no scheme check, no host check.



Impact: internal resource access (`http://localhost:8080/admin`),

cloud metadata (`http://169.254.169.254/`), file read via `file://`.



\### 2. Detection without reaction (CRITICAL)



`abused\_ssrf\_bug = true` is set but does not gate the fetch.

Self-flagged vulnerability remains active.



\### 3. Stored XSS via SVG (IMPORTANT)



Extension from URL suffix, not from `Content-Type`. `svg` in whitelist

→ stored XSS via `<script>` inside SVG.



\### 4. Fallback SSRF (IMPORTANT)



On fetch error, fallback persists raw attacker-controlled URL into

`UserModel.profileImage`.



\### 5. Missing: timeout, size cap, cleanup



No timeout, no size limit → DoS / disk exhaustion. No cleanup of

partial file on error.



\### 6. Concurrency



Race on same `userId` (`flags:'w'`), read-modify-write without transaction.



\### 7. Multi-instance break



Local disk not shared → breaks on horizontal scaling.



\## Resilience score: 2/10



\## Fix



\*\*Option A (immediate):\*\* URL allowlist + scheme check (http/https only)

\+ host allowlist + disable `file://` + `Content-Type` validation +

SVG rejection + timeout + size cap + cleanup.



\*\*Defense-in-depth:\*\* network egress policy (block 169.254.169.254,

localhost, internal subnets).



\## Why this matters



`npm audit` finds CVEs in dependencies. It does \*\*not\*\* find code logic flaws.

Vishap found SSRF + stored XSS + fallback SSRF in 50 lines of code.

