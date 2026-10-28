# -*- coding: utf-8 -*-
"""Tests for final_markdown SEC fallback (v6.1 P0 fix)."""
from src.pipeline.verdict import compute_risk_verdict


def test_sec_critical_in_markdown_triggers_review():
    stage2 = {"security": {"findings": []}, "threat_model": {"threats": []}, "risk_nodes": []}
    md = "[CONCLUSION] SEC-1 (критично): NULL-deref"
    rv, cv = compute_risk_verdict(stage2, pii=[], compliance=[], cwe_ids=[], final_markdown=md)
    assert rv == "REQUIRES_REVIEW"
    assert cv == "REQUIRES_REVIEW"


def test_sec_in_text_no_false_positive():
    stage2 = {}
    md = "No security issues here, just a normal description."
    rv, cv = compute_risk_verdict(stage2, pii=[], compliance=[], cwe_ids=[], final_markdown=md)
    assert rv == "SAFE"


def test_sec_fallback_only_when_structure_empty():
    # structure already has critical -> REQUIRES_REVIEW (structure wins)
    stage2 = {"security": {"findings": [{"priority": "критично"}]}}
    md = "[CONCLUSION] SEC-1 (критично)"
    rv, cv = compute_risk_verdict(stage2, pii=[], compliance=[], cwe_ids=[], final_markdown=md)
    assert rv == "REQUIRES_REVIEW"
