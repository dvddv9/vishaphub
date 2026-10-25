import ast, re, shutil, sys, subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\AI\conveyor_app")
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
DRY = "--dry-run" in sys.argv
SAST, PATTERNS, VERDICT = ROOT/"src/tools/sast.py", ROOT/"src/tools/patterns.py", ROOT/"src/pipeline/verdict.py"

def read(p): return p.read_text(encoding="utf-8")
def write(p,s):
    if not DRY: p.write_text(s, encoding="utf-8")
def backup(p):
    if not DRY: shutil.copy2(p, p.with_suffix(p.suffix+f".bak-{STAMP}"))
def ast_ok(p):
    try: ast.parse(read(p)); return True
    except SyntaxError as e: print(f"  [!] AST {p.name}: {e}"); return False
def fb(src,name):
    m = re.search(rf"^def {re.escape(name)}\s*\(", src, re.MULTILINE)
    if not m: return None
    s = m.start(); m2 = re.search(r"^def \w+\s*\(", src[s+1:], re.MULTILINE)
    return s, (s+1+m2.start() if m2 else len(src))
def after_doc(lines):
    in_doc, q = False, None
    for i,ln in enumerate(lines):
        if i==0: continue
        s = ln.strip()
        if not in_doc:
            if s.startswith('"""') or s.startswith("'''"):
                q = s[:3]
                if s.count(q)>=2 and len(s)>3: return i+1
                in_doc, last = True, i+1
        else:
            last = i+1
            if q in s: return last
    return 1

LOG = '''
# === LOG_PATTERNS (patch-logs) ===
LOG_PATTERNS = {
    "db_password":     re.compile(r"(postgres(?:ql)?|mysql|mongodb(?:\\\\+srv)?|redis)://[^:\\\\s]+:[^@\\\\s]+@"),
    "jwt_secret":      re.compile(r"JWT_SECRET\\\\s*=\\\\s*\\\\S+"),
    "aws_key":         re.compile(r"\\\\bAKIA[0-9A-Z]{16}\\\\b"),
    "aws_secret":      re.compile(r"AWS_SECRET_ACCESS_KEY\\\\s*=\\\\s*\\\\S+"),
    "stripe_key":      re.compile(r"\\\\b(sk|rk)_(live|test)_[A-Za-z0-9]+"),
    "pii_email":       re.compile(r"\\\\b[\\\\w.+-]+@[\\\\w-]+\\\\.[\\\\w.]+\\\\b"),
    "pii_phone":       re.compile(r"\\\\+?\\\\d[\\\\d\\\\s\\\\-]{8,}\\\\d"),
    "pii_passport_ru": re.compile(r"Passport RU:\\\\s*\\\\d{4}\\\\s*\\\\d{6}"),
    "credit_card":     re.compile(r"\\\\b(?:\\\\d[ -]*?){13,16}\\\\b"),
    "jwt_token":       re.compile(r"\\\\beyJ[A-Za-z0-9_-]+\\\\.[A-Za-z0-9_-]+\\\\.[A-Za-z0-9_-]*"),
    "ssh_key":         re.compile(r"-----BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY-----"),
    "sqlmap":          re.compile(r"sqlmap/"),
    "sqli_pattern":    re.compile(r"' OR '1'='1"),
    "cmd_injection":   re.compile(r"ping\\\\s+-c\\\\s+1\\\\s+\\\\S+;\\\\s*cat\\\\s+/etc/passwd"),
    "imdsv1":          re.compile(r"169\\\\.254\\\\.169\\\\.254"),
    "cors_wildcard":   re.compile(r"Access-Control-Allow-Origin:\\\\s*\\\\*"),
    "csp_wildcard":    re.compile(r"Content-Security-Policy:\\\\s*\\\\*"),
    "cookie_insecure": re.compile(r"HttpOnly=false|Secure=false"),
    "xff_trust":       re.compile(r"X-Forwarded-For:\\\\s*127\\\\.0\\\\.0\\\\.1"),
}
LOG_CWE_MAP = {
    "db_password":"CWE-798","jwt_secret":"CWE-798","aws_key":"CWE-798","aws_secret":"CWE-798",
    "stripe_key":"CWE-798","jwt_token":"CWE-522","ssh_key":"CWE-798","pii_email":"CWE-359",
    "pii_phone":"CWE-359","pii_passport_ru":"CWE-359","credit_card":"CWE-359","sqlmap":"CWE-200",
    "sqli_pattern":"CWE-89","cmd_injection":"CWE-78","imdsv1":"CWE-918","cors_wildcard":"CWE-942",
    "csp_wildcard":"CWE-1021","cookie_insecure":"CWE-1004","xff_trust":"CWE-348",
}
def is_log_material(material):
    return material.lstrip().startswith(("2026-","2025-","2024-"))
def scan_log(material):
    out = []
    for name, pat in LOG_PATTERNS.items():
        for m in pat.finditer(material):
            out.append({"type":name,"cwe":LOG_CWE_MAP.get(name),"match":m.group(0)[:80],
                        "line":material[:m.start()].count("\\\\n")+1})
    return out
# === /LOG_PATTERNS ===
'''

def p_sast():
    print("[1/3] sast.py")
    src = read(SAST); backup(SAST)
    if "LOG_PATTERNS" in src: print("  [=] уже есть")
    else:
        lines = src.splitlines(keepends=True)
        at = 0
        for i,ln in enumerate(lines):
            if ln.startswith(("import ","from ")) or ln.strip()=="": at = i+1
            else: break
        src = "".join(lines[:at]) + "\n" + LOG + "".join(lines[at:])
        print("  [+] LOG_PATTERNS")
    if re.search(r'ext\s*==\s*["\']log["\']', src): print("  [=] .log уже есть")
    else:
        m = re.search(r"def detect_language\s*\([^)]*\)[^:]*:", src)
        if m:
            rest = src[m.end():]
            lines = rest.splitlines(keepends=True)
            idx = after_doc(["def x():"]+lines)-1
            ins = '\n    if ext in ("log", "txt"): return "log"\n'
            src = src[:m.end()] + ins + src[m.end():]
            print("  [+] detect_language: .log")
        else: print("  [!] detect_language нет")
    write(SAST, src)
    if not DRY and not ast_ok(SAST):
        shutil.copy2(SAST.with_suffix(SAST.suffix+f".bak-{STAMP}"), SAST); sys.exit(1)

def p_patterns():
    print("[2/3] patterns.py")
    src = read(PATTERNS); backup(PATTERNS)
    b = fb(src, "detect_exploitability")
    if not b: print("  [!] detect_exploitability нет"); return
    s,e = b; f = src[s:e]
    if '"log"' in f or "is_log_material" in f: print("  [=] ветка логов есть"); return
    lines = f.splitlines(keepends=True)
    idx = after_doc(lines)
    br = '''    if material.lstrip().startswith(("2026-","2025-","2024-")):
        return {"reachable": True, "auth_required": False,
                "exploit_path": [{"type":"log","path":"log analysis"}],
                "blast_radius": "high",
                "entry_points": ["log file"],
                "blast_indicators": ["PII","secrets","SQLi/RCE traces","IMDS","privileged pod"]}

'''
    src = src[:s] + "".join(lines[:idx]) + br + "".join(lines[idx:]) + src[e:]
    write(PATTERNS, src)
    if not DRY and not ast_ok(PATTERNS):
        shutil.copy2(PATTERNS.with_suffix(PATTERNS.suffix+f".bak-{STAMP}"), PATTERNS); sys.exit(1)
    print("  [+] detect_exploitability: ветка логов")

def p_verdict():
    print("[3/3] verdict.py")
    src = read(VERDICT); backup(VERDICT)
    b = fb(src, "compute_reproducer")
    if not b: print("  [!] compute_reproducer нет"); return
    s,e = b; f = src[s:e]
    changed = False
    if "not provided (no queue_demo fixture)" in f:
        f = f.replace("not provided (no queue_demo fixture)","not provided (log: use log analysis / DLP scan)")
        changed = True; print("  [+] queue_demo -> log analysis")
    if "log analysis" not in f and "is_log_material" not in f:
        lines = f.splitlines(keepends=True)
        idx = after_doc(lines)
        br = '''    if context_thread and str((context_thread or {}).get("material","")).lstrip().startswith(("2026-","2025-","2024-")):
        return {"reproducer": None, "reproducer_verified": False,
                "reproducer_note": "not provided (log: use log analysis / DLP scan)"}

'''
        f = "".join(lines[:idx]) + br + "".join(lines[idx:])
        changed = True; print("  [+] compute_reproducer: skip логов")
    if not changed: print("  [=] нечего менять"); return
    src = src[:s] + f + src[e:]
    write(VERDICT, src)
    if not DRY and not ast_ok(VERDICT):
        shutil.copy2(VERDICT.with_suffix(VERDICT.suffix+f".bak-{STAMP}"), VERDICT); sys.exit(1)

def test():
    if DRY: print("[TEST] skip (dry)"); return
    print("[TEST] _test_log.py")
    t = ROOT/"_test_log.py"
    t.write_text('''from src.pipeline.verdict import compute_reproducer
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
''', encoding="utf-8")
    subprocess.run([sys.executable, str(t)], cwd=str(ROOT))

if __name__ == "__main__":
    print(f"=== patch-logs.py (stamp {STAMP}, dry={DRY}) ===")
    for p in (SAST, PATTERNS, VERDICT):
        if not p.exists(): print(f"[!] НЕТ: {p}"); sys.exit(1)
    p_sast(); p_patterns(); p_verdict(); test()
    print("=== DONE ===")
