# -*- coding: utf-8 -*-
"""Regression: risk_verdict must reflect stage2.security.findings.

Bug v5.10.6: run_audit looked ONLY at stage2.risk_nodes, ignoring
stage2.security.findings. LLM reports SEC-1/SEC-4 as separate findings
(not duplicated in risk_nodes). A file with critical SEC-N but no critical
RN-N would get SAFE -- false negative.

Dogfood: wcurl.1 case (2026-10-15). stage2.security = {summary, findings}.
findings[].priority in ("критично", "critical").
"""

from src.pipeline.orchestrator import run_audit


def _make_security(findings):
    """Helper: wrap findings into stage2.security shape."""
    return {"summary": "test summary", "findings": findings}


def _make_stage2(**kwargs):
    """Helper: build stage2_result dict."""
    return kwargs


# --- 1. Critical finding in security -> REQUIRES_REVIEW ---

def test_security_findings_critical_requires_review():
    stage2 = _make_stage2(
        risk_nodes=[],
        security=_make_security([
            {"id": "SEC-1", "issue": "cmdline injection", "priority": "критично"},
        ]),
    )
    audit = run_audit(material="def hello(): pass", session_id="sess-sec-1",
                      stage2_result=stage2)
    assert audit["risk_verdict"] == "REQUIRES_REVIEW"
    assert audit["critique_verdict"] == "REQUIRES_REVIEW"


# --- 2. Important finding -> SAFE ---

def test_security_findings_important_stays_safe():
    stage2 = _make_stage2(
        risk_nodes=[],
        security=_make_security([
            {"id": "SEC-2", "issue": "path traversal", "priority": "важно"},
        ]),
    )
    audit = run_audit(material="def hello(): pass", session_id="sess-sec-2",
                      stage2_result=stage2)
    assert audit["risk_verdict"] == "SAFE"


# --- 3. Optional finding -> SAFE ---

def test_security_findings_optional_stays_safe():
    stage2 = _make_stage2(
        risk_nodes=[],
        security=_make_security([
            {"id": "SEC-4", "issue": "no audit log", "priority": "опционально"},
        ]),
    )
    audit = run_audit(material="def hello(): pass", session_id="sess-sec-3",
                      stage2_result=stage2)
    assert audit["risk_verdict"] == "SAFE"


# --- 4. English "critical" -> REQUIRES_REVIEW ---

def test_security_english_critical_requires_review():
    stage2 = _make_stage2(
        risk_nodes=[],
        security=_make_security([
            {"id": "SEC-1", "issue": "cmdline injection", "priority": "critical"},
        ]),
    )
    audit = run_audit(material="def hello(): pass", session_id="sess-sec-4",
                      stage2_result=stage2)
    assert audit["risk_verdict"] == "REQUIRES_REVIEW"


# --- 5. security is not dict -> SAFE (fail-open) ---

def test_security_not_dict_stays_safe():
    stage2 = _make_stage2(risk_nodes=[], security="broken string")
    audit = run_audit(material="def hello(): pass", session_id="sess-sec-5",
                      stage2_result=stage2)
    assert audit["risk_verdict"] == "SAFE"


# --- 6. findings is not list -> SAFE (fail-open) ---

def test_security_findings_not_list_stays_safe():
    stage2 = _make_stage2(
        risk_nodes=[],
        security={"summary": "x", "findings": "not a list"},
    )
    audit = run_audit(material="def hello(): pass", session_id="sess-sec-6",
                      stage2_result=stage2)
    assert audit["risk_verdict"] == "SAFE"


# --- 7. risk_nodes critical + security critical -> REQUIRES_REVIEW (once) ---

def test_security_and_risk_nodes_dont_conflict():
    stage2 = _make_stage2(
        risk_nodes=[{"id": "RN-1", "priority": "критично", "note": "..."}],
        security=_make_security([
            {"id": "SEC-1", "issue": "cmdline injection", "priority": "критично"},
        ]),
    )
    audit = run_audit(material="def hello(): pass", session_id="sess-sec-7",
                      stage2_result=stage2)
    assert audit["risk_verdict"] == "REQUIRES_REVIEW"
    assert audit["critique_verdict"] == "REQUIRES_REVIEW"


# --- 8. Empty security dict -> SAFE ---

def test_security_empty_dict_stays_safe():
    stage2 = _make_stage2(risk_nodes=[], security={})
    audit = run_audit(material="def hello(): pass", session_id="sess-sec-8",
                      stage2_result=stage2)
    assert audit["risk_verdict"] == "SAFE"
