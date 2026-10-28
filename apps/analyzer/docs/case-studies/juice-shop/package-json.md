\# Juice Shop package.json — engineering hygiene issues



\*\*File:\*\* package.json (7.3 KB)

\*\*Cost:\*\* \~$0.007

\*\*Time:\*\* \~60 sec



\## Found



1\. \*\*FP-1 (CRITICAL)\*\* — `postinstall '|| cd .'` suppresses `build:server` errors → incomplete artifact could ship to prod.



2\. \*\*FP-2 (CRITICAL)\*\* — No lockfile pin, no `packageManager` → non-reproducible build, supply-chain risk.



3\. \*\*FP-3 (CRITICAL)\*\* — `jsonwebtoken 0.4.0`, `express-jwt 0.1.3` → auth bypass (alg confusion).



4\. \*\*FP-4 (IMPORTANT)\*\* — Invalid semver `@cyclonedx/cyclonedx-npm ^4.00` → silent SBOM failure.



5\. \*\*FP-5 (IMPORTANT)\*\* — SBOM covers root only, frontend out of scope.



6\. \*\*FP-6 (OPTIONAL)\*\* — `engines.node '22 - 26'` includes unstable versions.



\## Also



\- `pii\_detected: true` (email in maintainer fields).

\- `compliance\_flags: \['GDPR', '152-ФЗ']`.

\- 3 VERIFY markers (COVE).



\## Why this matters



`npm audit` found 19 vulnerabilities (12 low, 3 moderate, 4 high) — all CVEs in deps.

Vishap found 6 additional engineering issues that `npm audit` doesn't look for.

