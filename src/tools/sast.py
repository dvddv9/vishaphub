# -*- coding: utf-8 -*-
import re

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

    return {"language": language, "findings": findings, "count": len(findings)}

