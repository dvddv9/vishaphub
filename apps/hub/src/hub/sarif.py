"""SARIF 2.1.0 for a finished run, so a report can open in GitHub, Azure DevOps or an IDE.

The writer is the analyser's (`src.tools.sarif.to_sarif`): one implementation, borrowed
as a library, not copied. This module only translates the hub's run record into the
shape the writer expects — findings carry `id`, `title`, `severity`, `line`, it wants
`test_id`, `msg`, `severity`, `line`, `file`.

When the analyser is not in the image, `of_run` says so instead of inventing a format.
"""
from __future__ import annotations


def _findings(record: dict) -> list[dict]:
    result = record.get("result") if isinstance(record.get("result"), dict) else {}
    findings = result.get("findings")
    return findings if isinstance(findings, list) else []


def of_run(record: dict, source_file: str = "input") -> dict | None:
    """The run as SARIF, or ``None`` when the analyser's writer is not available."""
    try:
        from src.tools.sarif import to_sarif
    except ImportError:
        return None

    mapped = []
    for finding in _findings(record):
        if not isinstance(finding, dict):
            continue
        mapped.append({
            "test_id": str(finding.get("id") or finding.get("rule") or "vishap-rule"),
            "msg": str(finding.get("title") or finding.get("message") or "")[:200],
            "severity": str(finding.get("severity") or ""),
            "file": str(finding.get("file") or source_file),
            "line": int(finding.get("line") or 1),
        })

    audit = {
        "audit_id": str(record.get("id") or ""),
        "session_id": str(record.get("id") or ""),
        "critique_verdict": str(record.get("verdict") or ""),
        "pii_detected": bool((record.get("result") or {}).get("pii_detected")),
    }
    sast = {"vishap_rules": {"available": True, "findings": mapped}}
    return to_sarif(audit, sast_result=sast, source_file=source_file)
