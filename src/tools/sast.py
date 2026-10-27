


# -*- coding: utf-8 -*-
import re

# === LOG_PATTERNS (patch-logs) ===
LOG_PATTERNS = {
    "db_password":     re.compile(r"(postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^:\s]+:[^@\s]+@"),
    "jwt_secret":      re.compile(r"JWT_SECRET\s*=\s*\S+"),
    "aws_key":         re.compile(r"\bAKIA[0-9A-Z]{16,}\b"),
    "aws_secret":      re.compile(r"AWS_SECRET_ACCESS_KEY\s*=\s*\S+"),
    "stripe_key":      re.compile(r"\b(sk|rk)_(live|test)_[A-Za-z0-9]+"),
    "pii_email":       re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    # v7.4.7 #2: RU formats (+7 900 123 45 67, +7 (900) 123-45-67, 89001234567) and
    # "+"-prefixed international. Anchored: no match inside a longer digit run (epoch-ms ids).
    "pii_phone":       re.compile(r"(?<!\w)(?:\+?[78]\s*\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}|\+\d[\d\-]{8,14}\d)(?!\d)"),
    "pii_passport_ru": re.compile(r"Passport RU:\s*\d{4}\s*\d{6}"),
    "credit_card":     re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "jwt_token":       re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"),
    "ssh_key":         re.compile(r"-----BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY-----"),
    "sqlmap":          re.compile(r"sqlmap/"),
    "sqli_pattern":    re.compile(r"'\s*OR\s*'1'\s*=\s*'1|UNION\s+SELECT|'\s*OR\s*1\s*=\s*1", re.IGNORECASE),
    "cmd_injection":   re.compile(r"ping\s+-c\s+1\s+\S+;\s*cat|[;|]\s*cat\s+/etc/passwd"),
    "imdsv1":          re.compile(r"169\.254\.169\.254"),
    "cors_wildcard":   re.compile(r"Access-Control-Allow-Origin:\s*\*"),
    "csp_wildcard":    re.compile(r"Content-Security-Policy:\s*\*"),
    "cookie_insecure": re.compile(r"HttpOnly=false|Secure=false"),
    "xff_trust":       re.compile(r"X-Forwarded-For:\s*127\.0\.0\.1"),
}
LOG_CWE_MAP = {
    "db_password":"CWE-798","jwt_secret":"CWE-798","aws_key":"CWE-798","aws_secret":"CWE-798",
    "stripe_key":"CWE-798","jwt_token":"CWE-522","ssh_key":"CWE-798","pii_email":"CWE-359",
    "pii_phone":"CWE-359","pii_passport_ru":"CWE-359","credit_card":"CWE-359","sqlmap":"CWE-200",
    "sqli_pattern":"CWE-89","cmd_injection":"CWE-78","imdsv1":"CWE-918","cors_wildcard":"CWE-942",
    "csp_wildcard":"CWE-1021","cookie_insecure":"CWE-1004","xff_trust":"CWE-348",
}
def is_log_material(material: str) -> bool:
    """Эвристика: материал — лог, если начинается с timestamp."""
    return material.lstrip().startswith(("2026-","2025-","2024-"))

def luhn_ok(s: str) -> bool:
    """Luhn check for card-like numbers (13-19 digits); request ids and epoch-ms fail it."""
    digits = [int(c) for c in s if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def scan_log(material: str) -> list:
    """Сканирует лог LOG_PATTERNS, возвращает findings."""
    findings = []
    for name, pat in LOG_PATTERNS.items():
        for m in pat.finditer(material):
            if name == "credit_card" and not luhn_ok(m.group(0)):
                continue
            findings.append({
                "type": name,
                "cwe": LOG_CWE_MAP.get(name),
                "match": m.group(0)[:80],
                "line": material[:m.start()].count("\n")+1,
            })
    return findings
# === /LOG_PATTERNS ===


# ============ IaC patterns (FI > 0.25) ============
TF_PATTERNS = {
    "public_s3": re.compile(r"acl\s*=\s*['\"]public-read['\"]"),
    "open_sg": re.compile(r"cidr_blocks\s*=\s*\[['\"]0\.0\.0\.0/0['\"]\]"),
    "hardcoded_password": re.compile(r"password\s*=\s*['\"][^'\"]+['\"]"),
    "public_rds": re.compile(r"publicly_accessible\s*=\s*true"),
    "admin_iam": re.compile(r"Action\s*=\s*['\"]\*['\"]"),
    "curl_bash": re.compile(r"curl\s+.*\|\s*bash"),
    "imdsv1": re.compile(r"http_tokens\s*=\s*['\"]optional['\"]"),
}

K8S_PATTERNS = {
    "privileged": re.compile(r"privileged:\s*true"),
    "run_as_root": re.compile(r"runAsUser:\s*0"),
    "docker_sock": re.compile(r"/var/run/docker\.sock"),
    "host_path_root": re.compile(r"hostPath:\s*\n\s*path:\s*/"),
    "cluster_admin": re.compile(r"cluster-admin"),
    "latest_tag": re.compile(r"image:\s*.*:latest"),
}


def detect_language(filename: str, code: str = "") -> str:
    """Detect language by filename extension + content heuristics."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("log", "txt"): return "log"
    if ext in ("py", "pyw"): return "python"
    if ext in ("tf", "tfvars"): return "terraform"
    if ext in ("yaml", "yml"): return "yaml"
    if ext == "java": return "java"
    if ext in ("c", "h"): return "c"
    if ext in ("js", "jsx", "mjs", "cjs", "ts", "tsx"): return "javascript"
    if re.search(r"^\s*(def|import|from|class)\s+", code, re.M): return "python"
    if re.search(r"\bpublic\s+(class|interface)\b", code): return "java"
    if re.search(r"#include\s*<", code): return "c"
    return "unknown"

"""SAST integration — deterministic static analysis.

Dogfood P1 fix: LLM may miss issues. SAST is deterministic.
Run Bandit (Python) + Semgrep (multi-language) before/after LLM.
"""
import json
import shutil
import subprocess
from pathlib import Path


def _run_cmd(cmd: list, timeout: int = 60) -> tuple:
    """Run command, return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", "command not found"
    except subprocess.TimeoutExpired:
        return -2, "", "timeout"


def run_bandit(file_path: str, timeout: int = 60) -> dict:
    """Run Bandit on Python file. Returns normalized dict.

    Output: {
        "tool": "bandit",
        "available": bool,
        "findings": [{"line": int, "severity": str, "confidence": str, "test_id": str, "msg": str}],
        "summary": {"total": int, "high": int, "medium": int, "low": int},
    }
    """
    if not shutil.which("bandit"):
        return {"tool": "bandit", "available": False, "findings": [], "summary": {"total": 0}}

    if not Path(file_path).exists():
        return {"tool": "bandit", "available": True, "findings": [], "summary": {"total": 0}, "error": "file not found"}

    rc, stdout, stderr = _run_cmd(
        ["bandit", "-f", "json", "-q", file_path],
        timeout=timeout,
    )

    if rc < 0:
        return {"tool": "bandit", "available": True, "findings": [], "summary": {"total": 0}, "error": stderr}

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"tool": "bandit", "available": True, "findings": [], "summary": {"total": 0}, "error": "parse failed"}

    findings = []
    for r in data.get("results", []):
        findings.append({
            "line": r.get("line_number", 0),
            "severity": r.get("issue_severity", "UNKNOWN").lower(),
            "confidence": r.get("issue_confidence", "UNKNOWN").lower(),
            "test_id": r.get("test_id", ""),
            "msg": r.get("issue_text", ""),
        })

    summary = {"total": len(findings), "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = f.get("severity", "").lower()
        if sev in summary:
            summary[sev] += 1

    return {"tool": "bandit", "available": True, "findings": findings, "summary": summary}


def run_semgrep(file_path: str, timeout: int = 60) -> dict:
    """Run Semgrep with auto config. Returns normalized dict."""
    if not shutil.which("semgrep"):
        return {"tool": "semgrep", "available": False, "findings": [], "summary": {"total": 0}}

    if not Path(file_path).exists():
        return {"tool": "semgrep", "available": True, "findings": [], "summary": {"total": 0}, "error": "file not found"}

    rc, stdout, stderr = _run_cmd(
        ["semgrep", "--config=auto", "--json", "--quiet", file_path],
        timeout=timeout,
    )

    if rc < 0:
        return {"tool": "semgrep", "available": True, "findings": [], "summary": {"total": 0}, "error": stderr}

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"tool": "semgrep", "available": True, "findings": [], "summary": {"total": 0}, "error": "parse failed"}

    findings = []
    for r in data.get("results", []):
        findings.append({
            "line": r.get("start", {}).get("line", 0),
            "severity": r.get("extra", {}).get("severity", "UNKNOWN").lower(),
            "check_id": r.get("check_id", ""),
            "msg": r.get("extra", {}).get("message", ""),
        })

    summary = {"total": len(findings), "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        sev = f.get("severity", "").lower()
        if sev in summary:
            summary[sev] += 1

    return {"tool": "semgrep", "available": True, "findings": findings, "summary": summary}


def run_sast(file_path: str, language: str = "") -> dict:
    """Static SAST. Auto-detect language if not given."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as _f:
            _code = _f.read()
    except Exception:
        _code = ""

    if not language:
        language = detect_language(file_path, _code)

    findings = []

    if language == "terraform":
        for name, pat in TF_PATTERNS.items():
            for m in pat.finditer(_code):
                findings.append({"pattern": name, "line": _code[:m.start()].count("\n") + 1, "match": m.group()[:80]})
    elif language == "yaml":
        for name, pat in K8S_PATTERNS.items():
            for m in pat.finditer(_code):
                findings.append({"pattern": name, "line": _code[:m.start()].count("\n") + 1, "match": m.group()[:80]})
    elif language == "python":
        for name, pat in CRITICAL_RISK_PATTERNS.items():
            for m in pat.finditer(_code):
                findings.append({"pattern": name, "line": _code[:m.start()].count("\n") + 1, "match": m.group()[:80]})
    elif language == "javascript":
        for name, pat in JS_PATTERNS.items():
            for m in pat.finditer(_code):
                findings.append({"pattern": name, "line": _code[:m.start()].count("\n") + 1, "match": m.group()[:80]})

    # The pipeline reads total_findings / high_priority / engine / cwe_ids
    # (orchestrator.run_audit); returning only `count` made every SAST hit
    # invisible to the verdict. Keep `count` for older callers.
    critical = {"eval", "exec", "shell", "pickle", "deserialization", "hardcoded"}
    high_priority = sum(1 for f in findings if any(k in f.get("pattern", "").lower() for k in critical))
    return {
        "language": language,
        "findings": findings,
        "count": len(findings),
        "total_findings": len(findings),
        "high_priority": high_priority,
        "engine": "static-scan" if findings or language in ("python", "javascript", "terraform", "yaml") else "",
        "cwe_ids": [],
    }

