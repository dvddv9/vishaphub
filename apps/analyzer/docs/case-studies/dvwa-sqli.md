# DVWA low.php — SQL injection
**File:** vulnerabilities/sqli/source/low.php (~55 LOC) | **Level:** D2 | **Cost:** ~$0.007
## Found
- CRITICAL: SQLi via \['id'] in MYSQL and SQLITE branches
- CRITICAL: No CSRF / authz
- CRITICAL: Irreversible data leak
- IMPORTANT: DB errors leak to client (mysqli_error, getMessage)
- IMPORTANT: SQLite else-branch uses undefined \
## STRIDE: T, I, S, D, E, R — 6 threats
