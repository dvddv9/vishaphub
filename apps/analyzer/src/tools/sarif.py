# -*- coding: utf-8 -*-
"""SARIF 2.1.0 output — standard format for security findings.

Dogfood P1: integrate with GitHub Code Scanning / Azure DevOps / IDE.
SARIF spec: https://docs.oasis-open.org/sarif/sarif/v2.1.0/
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from src.tools.baseline import compute_fingerprint


def _severity_to_sarif_level(severity: str) -> str:
    """Map tool severity to SARIF level."""
    s = (severity or "").lower()
    return {
        "high": "error",
        "critical": "error",
        "medium": "warning",
        "moderate": "warning",
        "low": "note",
        "info": "note",
    }.get(s, "warning")


def to_sarif(audit: dict, sast_result: dict = None, sca_result: dict = None,
             source_file: str = "input", risk_nodes: list = None) -> dict:
    """Convert Vishap audit + SAST/SCA results to SARIF 2.1.0.

    Args:
        audit: audit dict from run_audit
        sast_result: dict from src.tools.sast.run_sast
        sca_result: dict from src.tools.sca.run_sca
        source_file: filename for SARIF artifacts

    Returns:
        SARIF JSON as dict.
    """
    rules = []
    results = []

    # === SAST findings (Bandit, Semgrep) ===
    if sast_result:
        for tool_name in ("bandit", "semgrep", "vishap_rules"):
            tool_result = sast_result.get(tool_name)
            if not tool_result or not tool_result.get("available"):
                continue

            for i, f in enumerate(tool_result.get("findings", [])):
                rule_id = f.get("test_id") or f.get("check_id") or f"{tool_name}_unknown"
                rule_id_full = f"{tool_name}/{rule_id}"

                rules.append({
                    "id": rule_id_full,
                    "name": rule_id,
                    "shortDescription": {"text": f.get("msg", "")[:200]},
                    "defaultConfiguration": {
                        "level": _severity_to_sarif_level(f.get("severity", "")),
                    },
                    "properties": {
                        "source": tool_name,
                        "severity": f.get("severity", ""),
                        "confidence": f.get("confidence", ""),
                    },
                })

                _fp_input = {
                    "name": str(rule_id),
                    "priority": str(f.get("severity", "")),
                    "note": str(f.get("msg", ""))[:100],
                }
                _fp = f.get("fingerprint") or compute_fingerprint(_fp_input, source_file)
                _props = {k: f[k] for k in ("kind", "status", "evidence") if f.get(k)}
                results.append({
                    "ruleId": rule_id_full,
                    "level": _severity_to_sarif_level(f.get("severity", "")),
                    **({"properties": _props} if _props else {}),
                    "message": {"text": f.get("msg", "")},
                    "locations": [{
                        "physicalLocation": {
                            "artifactLocation": {"uri": f.get("file") or source_file},
                            "region": {"startLine": f.get("line", 1) or 1},
                        }
                    }],
                    "partialFingerprints": {
                        "vishapFingerprint/v1": _fp,
                    },
                })

    # === SCA vulnerabilities (pip-audit) ===
    if sca_result:
        pa = sca_result.get("pip_audit")
        if pa and pa.get("available"):
            for v in pa.get("vulnerabilities", []):
                rule_id = f"pip-audit/{v.get('id', 'UNKNOWN')}"
                rules.append({
                    "id": rule_id,
                    "name": v.get("id", ""),
                    "shortDescription": {
                        "text": f"{v.get('name', '')}=={v.get('version', '')}: {v.get('description', '')[:150]}"
                    },
                    "defaultConfiguration": {"level": "error"},
                    "properties": {
                        "source": "pip-audit",
                        "package": v.get("name", ""),
                        "version": v.get("version", ""),
                        "fix_versions": v.get("fix_versions", []),
                    },
                })
                _fp_input = {
                    "name": str(v.get("name", "")),
                    "priority": "high",
                    "note": str(v.get("id", ""))[:100],
                }
                _fp = compute_fingerprint(_fp_input, "requirements.txt")
                results.append({
                    "ruleId": rule_id,
                    "level": "error",
                    "message": {
                        "text": f"{v.get('name', '')}=={v.get('version', '')}: {v.get('id', '')}"
                    },
                    "locations": [{
                        "physicalLocation": {
                            "artifactLocation": {"uri": "requirements.txt"},
                        }
                    }],
                    "partialFingerprints": {
                        "vishapFingerprint/v1": _fp,
                    },
                })

    # === Risk nodes (Stage 2 LLM analysis) ===
    if risk_nodes and isinstance(risk_nodes, list):
        for rn in risk_nodes:
            if not isinstance(rn, dict):
                continue
            rn_name = str(rn.get("name", "risk"))
            rn_priority = str(rn.get("priority", "warning"))
            rn_note = str(rn.get("note", ""))
            slug = "".join(c if c.isalnum() else "_" for c in rn_name.lower())[:40]
            rule_id = f"vishap/risk/{slug}"
            level = _severity_to_sarif_level(rn_priority)
            fp = compute_fingerprint(rn, source_file)
            rules.append({
                "id": rule_id,
                "name": rn_name[:80],
                "shortDescription": {"text": rn_name[:200]},
                "fullDescription": {"text": rn_note[:500]},
                "defaultConfiguration": {"level": level},
                "properties": {
                    "source": "vishap/stage2",
                    "priority": rn_priority,
                },
            })
            results.append({
                "ruleId": rule_id,
                "level": level,
                "message": {"text": rn_note[:500] or rn_name},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": source_file},
                    }
                }],
                "partialFingerprints": {
                    "vishapFingerprint/v1": fp,
                },
            })

    # === Vishap audit metadata as SARIF properties ===
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "Vishap",
                    "version": "6.0.1",
                    "informationUri": "https://github.com/dvddv9/vishap",
                    "rules": rules,
                }
            },
            "results": results,
            "invocations": [{
                "executionSuccessful": True,
                "startTimeUtc": datetime.now(timezone.utc).isoformat(),
            }],
            "properties": {
                "vishap": {
                    "audit_id": audit.get("audit_id", ""),
                    "session_id": audit.get("session_id", ""),
                    "material_hash": audit.get("material_hash", ""),
                    "material_hash_full": audit.get("material_hash_full", ""),
                    "critique_verdict": audit.get("critique_verdict", ""),
                    "risk_verdict": audit.get("risk_verdict", ""),
                    "pii_detected": audit.get("pii_detected", False),
                    "compliance_flags": audit.get("compliance_flags", []),
                    "sast_findings": audit.get("sast_findings", 0),
                    "sca_vulnerabilities": audit.get("sca_vulnerabilities", 0),
                },
            },
        }],
    }

    return sarif


def write_sarif(sarif: dict, output_path: str) -> str:
    """Write SARIF JSON to file. Returns path."""
    p = Path(output_path)
    p.write_text(json.dumps(sarif, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(p)
