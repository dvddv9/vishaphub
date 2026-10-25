# -*- coding: utf-8 -*-
import re

def detect_language(filename: str, code: str = "") -> str:
    """Detect language by filename extension + content heuristics."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("py", "pyw"): return "python"
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
    if not language:
        try:
            with open(file_path, encoding="utf-8", errors="replace") as _f:
                _code = _f.read()
            language = detect_language(file_path, _code)
        except Exception:
            pass
    """Static SAST. Auto-detect language if not given."""
    if not language:
        try:
            with open(file_path, encoding="utf-8", errors="replace") as _f:
                _code = _f.read()
            language = detect_language(file_path, _code)
        except Exception:
            pass
    """Static SAST scan. Language auto-detected if not given."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as _f:
            _code = _f.read()
    except Exception:
        _code = ""
    if not language:
        language = detect_language(file_path, _code)
    # ... остальное тело функции
    """Run all available SAST tools for given file.

    Returns combined dict:
    {
        "bandit": {...},
        "semgrep": {...},
        "total_findings": int,
        "high_priority": int,
    }
    """
    result = {"bandit": None, "semgrep": None}

    if language == "python":
        result["bandit"] = run_bandit(file_path)

    result["semgrep"] = run_semgrep(file_path)

    total = 0
    high = 0
    for tool in ("bandit", "semgrep"):
        t = result.get(tool)
        if t and t.get("available"):
            total += t.get("summary", {}).get("total", 0)
            high += t.get("summary", {}).get("high", 0)

    result["total_findings"] = total
    result["high_priority"] = high
    return result
