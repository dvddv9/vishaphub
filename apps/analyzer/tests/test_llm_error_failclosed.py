# -*- coding: utf-8 -*-
"""The LLM gate must fail closed.

The desktop app used to produce a report that said `critique_verdict: SAFE` with
the model never saw. These tests pin the opposite contract.
"""
from src.pipeline.orchestrator import (
    LLM_UNAVAILABLE_BANNER,
    llm_error_of,
    run_audit,
)


def test_error_mode_is_detected():
    assert llm_error_of({"mode": "error", "text": "[LLM error] x"})
    assert llm_error_of({"mode": "custom", "text": "[LLM error] boom"})
    assert llm_error_of("[LLM error] boom")
    assert llm_error_of("  [LLM error] boom")


def test_clean_stages_are_not_errors():
    assert llm_error_of({"mode": "custom", "text": "# Report\n..."}) is None
    assert llm_error_of("# Report\n...") is None
    assert llm_error_of(None) is None
    assert llm_error_of({}) is None


def test_audit_fails_closed_when_the_model_was_not_reached():
    audit = run_audit(
        "print(1)", "sess-test",
        llm_error="[LLM error] DSH endpoint is unreachable",
    )
    assert audit["critique_verdict"] == "ERROR"
    assert audit["risk_verdict"] == "REQUIRES_REVIEW"
    assert audit["llm_error"] is True


def test_audit_stays_normal_when_the_model_answered():
    audit = run_audit("print(1)", "sess-test")
    assert audit["critique_verdict"] in ("SAFE", "REQUIRES_REVIEW", "NEEDS_VERIFICATION")
    assert audit["llm_error"] is False


def test_banner_explains_the_failure_in_the_report():
    text = LLM_UNAVAILABLE_BANNER.format(error="[LLM error] 401")
    assert "Анализ не выполнен" in text
    assert "CUSTOM_LLM_URL" in text
    assert "[LLM error] 401" in text
