# -*- coding: utf-8 -*-
"""Tests for threat_model-based verdict (v6.1 P0 fix)."""
from src.pipeline.verdict import compute_risk_verdict


def test_critical_in_threat_model_triggers_review():
    stage2 = {"threat_model": {"threats": [{"priority": "критично"}]}}
    rv, cv = compute_risk_verdict(stage2, pii=[], compliance=[], cwe_ids=[])
    assert rv == "REQUIRES_REVIEW"
    assert cv == "REQUIRES_REVIEW"


def test_no_critical_in_threat_model_returns_safe():
    stage2 = {
        "threat_model": {"threats": [{"priority": "важно"}]},
        "security": {},
        "risk_nodes": [],
    }
    rv, cv = compute_risk_verdict(stage2, pii=[], compliance=[], cwe_ids=[])
    assert rv == "SAFE"


def test_threat_model_empty_still_works():
    stage2 = {}  # no threat_model field at all
    rv, cv = compute_risk_verdict(stage2, pii=[], compliance=[], cwe_ids=[])
    assert rv == "SAFE"


def test_threat_model_and_security_both_empty_safe():
    stage2 = {
        "threat_model": {"threats": [{"priority": "важно"}]},
        "security": {"findings": [{"priority": "важно"}]},
    }
    rv, cv = compute_risk_verdict(stage2, pii=[], compliance=[], cwe_ids=[])
    assert rv == "SAFE"
