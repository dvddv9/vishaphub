# -*- coding: utf-8 -*-
"""Unit tests for src/pipeline/verdict.py.

Tests the consolidated compute_risk_verdict() -- single source of truth
for (risk_verdict, critique_verdict).
"""
from src.pipeline.verdict import (
    compute_risk_verdict,
    _has_critical_priority,
    _has_critical_risk_nodes,
    _has_critical_security,
)


# ============================================================
# _has_critical_priority
# ============================================================

def test_critical_priority_russian():
    assert _has_critical_priority([{"priority": "критично"}]) is True


def test_critical_priority_english():
    assert _has_critical_priority([{"priority": "critical"}]) is True


def test_critical_priority_important_not_critical():
    assert _has_critical_priority([{"priority": "важно"}]) is False


def test_critical_priority_not_list():
    assert _has_critical_priority("not a list") is False


def test_critical_priority_non_dict_items():
    assert _has_critical_priority(["str", None, 42]) is False


def test_critical_priority_empty_list():
    assert _has_critical_priority([]) is False


# ============================================================
# _has_critical_risk_nodes
# ============================================================

def test_risk_nodes_critical():
    stage2 = {"risk_nodes": [{"id": "RN-1", "priority": "критично"}]}
    assert _has_critical_risk_nodes(stage2) is True


def test_risk_nodes_not_critical():
    stage2 = {"risk_nodes": [{"id": "RN-1", "priority": "важно"}]}
    assert _has_critical_risk_nodes(stage2) is False


def test_risk_nodes_none_stage2():
    assert _has_critical_risk_nodes(None) is False


def test_risk_nodes_empty_stage2():
    assert _has_critical_risk_nodes({}) is False


# ============================================================
# _has_critical_security
# ============================================================

def test_security_critical():
    stage2 = {"security": {"findings": [{"id": "SEC-1", "priority": "critical"}]}}
    assert _has_critical_security(stage2) is True


def test_security_not_critical():
    stage2 = {"security": {"findings": [{"id": "SEC-2", "priority": "важно"}]}}
    assert _has_critical_security(stage2) is False


def test_security_not_dict():
    stage2 = {"security": "broken"}
    assert _has_critical_security(stage2) is False


def test_security_findings_not_list():
    stage2 = {"security": {"findings": "not a list"}}
    assert _has_critical_security(stage2) is False


def test_security_missing_findings():
    stage2 = {"security": {"summary": "x"}}
    assert _has_critical_security(stage2) is False


# ============================================================
# compute_risk_verdict -- priority order
# ============================================================

def test_emergency_overrides_all():
    stage2 = {"risk_nodes": [{"priority": "critical"}], "security": {"findings": [{"priority": "critical"}]}}
    rv, cv = compute_risk_verdict(stage2, pii=[1], compliance=[1], cwe_ids=[1], force_emergency=True)
    assert rv == "EMERGENCY"
    assert cv == "EMERGENCY"


def test_pii_triggers_review():
    rv, cv = compute_risk_verdict(None, pii=[{"email": "x@y.z"}], compliance=[], cwe_ids=[])
    assert rv == "REQUIRES_REVIEW"
    assert cv == "REQUIRES_REVIEW"


def test_compliance_triggers_review():
    rv, cv = compute_risk_verdict(None, pii=[], compliance=[{"gdpr": 1}], cwe_ids=[])
    assert rv == "REQUIRES_REVIEW"


def test_cwe_triggers_review():
    rv, cv = compute_risk_verdict(None, pii=[], compliance=[], cwe_ids=["CWE-89"])
    assert rv == "REQUIRES_REVIEW"


def test_critical_risk_node_triggers_review():
    stage2 = {"risk_nodes": [{"id": "RN-1", "priority": "критично"}]}
    rv, cv = compute_risk_verdict(stage2, pii=[], compliance=[], cwe_ids=[])
    assert rv == "REQUIRES_REVIEW"
    assert cv == "REQUIRES_REVIEW"


def test_critical_security_triggers_review():
    stage2 = {"security": {"findings": [{"id": "SEC-1", "priority": "critical"}]}}
    rv, cv = compute_risk_verdict(stage2, pii=[], compliance=[], cwe_ids=[])
    assert rv == "REQUIRES_REVIEW"
    assert cv == "REQUIRES_REVIEW"


def test_no_signals_safe():
    rv, cv = compute_risk_verdict(None, pii=[], compliance=[], cwe_ids=[])
    assert rv == "SAFE"
    assert cv == "SAFE"


def test_important_only_safe():
    stage2 = {"risk_nodes": [{"priority": "важно"}]}
    rv, cv = compute_risk_verdict(stage2, pii=[], compliance=[], cwe_ids=[])
    assert rv == "SAFE"


def test_optional_only_safe():
    stage2 = {"risk_nodes": [{"priority": "опционально"}]}
    rv, cv = compute_risk_verdict(stage2, pii=[], compliance=[], cwe_ids=[])
    assert rv == "SAFE"


def test_stage2_none_safe():
    rv, cv = compute_risk_verdict(None, pii=[], compliance=[], cwe_ids=[])
    assert rv == "SAFE"


def test_pii_priority_over_critical_risk_nodes():
    """pii/compliance/cwe checked BEFORE risk_nodes."""
    stage2 = {"risk_nodes": [{"priority": "critical"}]}
    rv, cv = compute_risk_verdict(stage2, pii=["x"], compliance=[], cwe_ids=[])
    assert rv == "REQUIRES_REVIEW"
