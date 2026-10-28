# -*- coding: utf-8 -*-
"""SCA integration — dependency vulnerability scanning.

Dogfood P1 fix: requirements.txt uses >= without pinning.
Run pip-audit to find CVEs in dependencies.
"""
import json
import shutil
import subprocess
from pathlib import Path


def run_pip_audit(requirements_path: str = "requirements.txt", timeout: int = 120) -> dict:
    """Run pip-audit on requirements.txt. Returns normalized dict.

    Output: {
        "tool": "pip-audit",
        "available": bool,
        "vulnerabilities": [{"name": str, "version": str, "id": str, "fix_versions": [str], "description": str}],
        "summary": {"total": int, "critical": int, "high": int, "moderate": int, "low": int},
    }
    """
    if not shutil.which("pip-audit"):
        return {"tool": "pip-audit", "available": False, "vulnerabilities": [], "summary": {"total": 0}}

    if not Path(requirements_path).exists():
        return {"tool": "pip-audit", "available": True, "vulnerabilities": [], "summary": {"total": 0}, "error": "file not found"}

    try:
        r = subprocess.run(
            ["pip-audit", "-r", requirements_path, "-f", "json", "--progress-spinner", "off"],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        return {"tool": "pip-audit", "available": False, "vulnerabilities": [], "summary": {"total": 0}}
    except subprocess.TimeoutExpired:
        return {"tool": "pip-audit", "available": True, "vulnerabilities": [], "summary": {"total": 0}, "error": "timeout"}

    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"tool": "pip-audit", "available": True, "vulnerabilities": [], "summary": {"total": 0}, "error": "parse failed"}

    vulns = []
    deps = data.get("dependencies", []) if isinstance(data, dict) else data
    if isinstance(deps, list):
        for dep in deps:
            for v in dep.get("vulns", []):
                vulns.append({
                    "name": dep.get("name", ""),
                    "version": dep.get("version", ""),
                    "id": v.get("id", ""),
                    "fix_versions": v.get("fix_versions", []),
                    "description": (v.get("description", "") or "")[:200],
                })

    return {
        "tool": "pip-audit",
        "available": True,
        "vulnerabilities": vulns,
        "summary": {"total": len(vulns)},
    }


def run_sca(requirements_path: str = "requirements.txt") -> dict:
    """Run SCA (dependency audit)."""
    return {"pip_audit": run_pip_audit(requirements_path)}
