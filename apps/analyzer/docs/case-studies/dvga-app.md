# DVGA app.py — hardcoded secrets + RCE
**File:** app.py (~40 LOC) | **Level:** D2 | **Cost:** ~$0.007
## Found
- CRITICAL: JWT_SECRET_KEY='dvga' — forge JWT (incl admin)
- CRITICAL: SECRET_KEY='dvga' — forge session cookie
- CRITICAL: os.popen('python3 setup.py') — RCE at startup
- IMPORTANT: refresh TTL (30s) < access TTL (120s) — broken refresh flow
- IMPORTANT: sys.setrecursionlimit(100000) under gevent — segfault
## Fix
Env vars + secret manager, remove os.popen, fix TTL, return recursionlimit.
