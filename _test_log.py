from src.pipeline.verdict import compute_reproducer
from src.tools.patterns import detect_exploitability
LOG = """2026-10-25 18:00:02 INFO [app] DB connection: postgresql://admin:admin123@db.prod.internal:5432/app
2026-10-25 18:00:04 INFO [app] AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
2026-10-25 18:00:06 DEBUG [app] User input: name=' OR '1'='1
2026-10-25 18:00:13 INFO [app] User email: john.doe@example.com, phone: +1-555-123-4567
2026-10-25 18:00:17 INFO [app] AWS metadata: http://169.254.169.254/latest/meta-data/
2026-10-25 18:00:22 INFO [app] X-Forwarded-For: 127.0.0.1, 10.0.0.1
2026-10-25 18:00:25 ERROR [app] Cookie: session=abc123; HttpOnly=false; Secure=false
"""
print("reproducer:", compute_reproducer(None, None, LOG))
print("exploitability:", detect_exploitability(LOG))
try:
    from src.tools.sast import scan_log, is_log_material, LOG_PATTERNS
    print("is_log_material:", is_log_material(LOG))
    print("LOG_PATTERNS:", len(LOG_PATTERNS))
    print("findings:", len(scan_log(LOG)))
except Exception as e:
    print("scan_log ERROR:", e)
