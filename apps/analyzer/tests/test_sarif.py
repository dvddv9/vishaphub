# -*- coding: utf-8 -*-
"""Tests for SARIF output (P1-4)."""
from src.tools.sarif import to_sarif, write_sarif, _severity_to_sarif_level


def _rn(name="test risk", priority="критично", note="hello world"):
    return {"id": "RN-1", "name": name, "priority": priority, "note": note}


def test_severity_mapping():
    assert _severity_to_sarif_level("critical") == "error"
    assert _severity_to_sarif_level("high") == "error"
    assert _severity_to_sarif_level("medium") == "warning"
    assert _severity_to_sarif_level("low") == "note"
    assert _severity_to_sarif_level("unknown") == "warning"
    assert _severity_to_sarif_level("") == "warning"


def test_to_sarif_empty_audit():
    s = to_sarif(audit={})
    assert s["version"] == "2.1.0"
    assert len(s["runs"]) == 1
    assert s["runs"][0]["results"] == []


def test_to_sarif_risk_nodes_basic():
    s = to_sarif(audit={"audit_id": "x"}, risk_nodes=[_rn()])
    run = s["runs"][0]
    assert len(run["results"]) == 1
    assert len(run["tool"]["driver"]["rules"]) == 1
    assert run["results"][0]["ruleId"].startswith("vishap/risk/")


def test_to_sarif_partial_fingerprints_present():
    s = to_sarif(audit={}, risk_nodes=[_rn()])
    result = s["runs"][0]["results"][0]
    assert "partialFingerprints" in result
    fp = result["partialFingerprints"]["vishapFingerprint/v1"]
    assert len(fp) == 16


def test_to_sarif_risk_nodes_not_list():
    s = to_sarif(audit={}, risk_nodes="not a list")
    assert s["runs"][0]["results"] == []


def test_to_sarif_risk_nodes_invalid_items():
    s = to_sarif(audit={}, risk_nodes=[None, "x", {"name": "ok"}])
    assert len(s["runs"][0]["results"]) == 1


def test_to_sarif_multiple_risk_nodes():
    s = to_sarif(audit={}, risk_nodes=[
        _rn(name="a", priority="критично"),
        _rn(name="b", priority="важно"),
    ])
    assert len(s["runs"][0]["results"]) == 2


def test_write_sarif(tmp_path):
    s = to_sarif(audit={}, risk_nodes=[_rn()])
    out = tmp_path / "out.sarif"
    write_sarif(s, str(out))
    assert out.exists()
    assert "vishap/risk/" in out.read_text(encoding="utf-8")


def test_to_sarif_audit_metadata_preserved():
    s = to_sarif(audit={"audit_id": "abc-123", "risk_verdict": "REQUIRES_REVIEW"})
    props = s["runs"][0]["properties"]["vishap"]
    assert props["audit_id"] == "abc-123"
    assert props["risk_verdict"] == "REQUIRES_REVIEW"
