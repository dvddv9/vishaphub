# -*- coding: utf-8 -*-
"""Regression: risk_verdict must reflect LLM critical risk_nodes.

Bug v5.8-v5.10.5: run_audit computed risk_verdict ONLY from pii/compliance/cwe_ids,
ignoring stage2.risk_nodes. LLM found critical risks (priority='критично')
but risk_verdict stayed SAFE -- UI showed green SAFE despite critical report.
Dogfood: RequestFilter.java case (2026-10-14).
"""
import inspect

from src.pipeline.orchestrator import run_audit


def test_run_audit_accepts_stage2_result():
    sig = inspect.signature(run_audit)
    assert "stage2_result" in sig.parameters


def test_risk_verdict_requires_review_on_critical_node():
    stage2 = {"risk_nodes": [{"id": "RN-1", "priority": "критично", "note": "..."}]}
    audit = run_audit(material="def hello(): pass", session_id="sess-test-1", stage2_result=stage2)
    assert audit["risk_verdict"] == "REQUIRES_REVIEW"
    assert audit["critique_verdict"] == "REQUIRES_REVIEW"


def test_risk_verdict_requires_review_on_english_critical():
    stage2 = {"risk_nodes": [{"id": "SEC-1", "priority": "critical", "note": "..."}]}
    audit = run_audit(material="def hello(): pass", session_id="sess-test-2", stage2_result=stage2)
    assert audit["risk_verdict"] == "REQUIRES_REVIEW"


def test_risk_verdict_safe_without_critical_nodes():
    stage2 = {"risk_nodes": [
        {"id": "RN-1", "priority": "важно", "note": "..."},
        {"id": "RN-2", "priority": "опционально", "note": "..."},
    ]}
    audit = run_audit(material="def hello(): pass", session_id="sess-test-3", stage2_result=stage2)
    assert audit["risk_verdict"] == "SAFE"


def test_risk_verdict_ignores_non_dict_nodes():
    stage2 = {"risk_nodes": ["not a dict", None, 42]}
    audit = run_audit(material="def hello(): pass", session_id="sess-test-4", stage2_result=stage2)
    assert audit["risk_verdict"] == "SAFE"


def test_risk_verdict_emergency_overrides_critical():
    stage2 = {"risk_nodes": [{"id": "RN-1", "priority": "критично", "note": "..."}]}
    audit = run_audit(material="def hello(): pass", session_id="sess-test-5",
                      force_emergency=True, stage2_result=stage2)
    assert audit["risk_verdict"] == "EMERGENCY"


def test_risk_verdict_no_stage2_backward_compat():
    audit = run_audit(material="def hello(): pass", session_id="sess-test-6")
    assert audit["risk_verdict"] == "SAFE"
