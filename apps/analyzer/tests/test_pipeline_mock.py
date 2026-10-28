# -*- coding: utf-8 -*-
"""Integration tests with mocked LLM (no real API calls)."""
from unittest.mock import patch

from src.pipeline import orchestrator


MOCK_STAGE0 = {
    "level": "D0",
    "route": [],
    "research_first": False,
    "subst_count": 0,
    "flags": [],
    "_meta": {"tokens_in": 10, "tokens_out": 5},
}
MOCK_STAGE1 = {
    "files": [],
    "deps": [],
    "_meta": {"tokens_in": 10, "tokens_out": 5},
}
MOCK_STAGE2 = {
    "risk_nodes": [],
    "resilience_score": 8,
    "_meta": {"tokens_in": 10, "tokens_out": 5},
}
MOCK_STAGE4 = {
    "options": [],
    "force_emergency": False,
    "_meta": {"tokens_in": 10, "tokens_out": 5},
}
MOCK_STAGE5 = (
    "# D0 — foo()\n\n"
    "[CONCLUSION] Test conclusion.\n"
    "[RISK] No risks.\n"
    "[FUNC:FULL]\n"
    "- ECON: effort ~5 min, cost $0, ROI high.\n"
)


@patch("src.pipeline.orchestrator.stage5_transmitter", return_value=MOCK_STAGE5)
@patch("src.pipeline.orchestrator.stage4_synthesizer", return_value=MOCK_STAGE4)
@patch("src.pipeline.orchestrator.stage2_analyst", return_value=MOCK_STAGE2)
@patch("src.pipeline.orchestrator.stage1_scanner", return_value=MOCK_STAGE1)
@patch("src.pipeline.orchestrator.stage0_orchestrator", return_value=MOCK_STAGE0)
def test_run_pipeline_has_keys(s0, s1, s2, s4, s5):
    result = orchestrator.run_pipeline("def foo(): pass", "a.py", verbose=False)
    assert "session_id" in result
    assert "audit" in result
    assert "completeness" in result
    assert "final_markdown" in result


@patch("src.pipeline.orchestrator.stage5_transmitter", return_value=MOCK_STAGE5)
@patch("src.pipeline.orchestrator.stage4_synthesizer", return_value=MOCK_STAGE4)
@patch("src.pipeline.orchestrator.stage2_analyst", return_value=MOCK_STAGE2)
@patch("src.pipeline.orchestrator.stage1_scanner", return_value=MOCK_STAGE1)
@patch("src.pipeline.orchestrator.stage0_orchestrator", return_value=MOCK_STAGE0)
def test_audit_structure(s0, s1, s2, s4, s5):
    result = orchestrator.run_pipeline("def foo(): pass", "a.py", verbose=False)
    audit = result["audit"]
    assert "audit_id" in audit
    assert "material_hash" in audit
    assert "pii_detected" in audit
    assert "critique_verdict" in audit
    assert audit["critique_verdict"] in ("SAFE", "REQUIRES_REVIEW", "NEEDS_VERIFICATION")


@patch("src.pipeline.orchestrator.stage5_transmitter", return_value=MOCK_STAGE5)
@patch("src.pipeline.orchestrator.stage4_synthesizer", return_value=MOCK_STAGE4)
@patch("src.pipeline.orchestrator.stage2_analyst", return_value=MOCK_STAGE2)
@patch("src.pipeline.orchestrator.stage1_scanner", return_value=MOCK_STAGE1)
@patch("src.pipeline.orchestrator.stage0_orchestrator", return_value=MOCK_STAGE0)
def test_completeness_structure(s0, s1, s2, s4, s5):
    result = orchestrator.run_pipeline("def foo(): pass", "a.py", verbose=False)
    c = result["completeness"]
    assert "level" in c
    assert "loss_pct" in c
    assert "verdict" in c
    assert c["verdict"] in ("ACCEPTABLE", "INCOMPLETE")


@patch("src.pipeline.orchestrator.stage5_transmitter", return_value=MOCK_STAGE5)
@patch("src.pipeline.orchestrator.stage4_synthesizer", return_value=MOCK_STAGE4)
@patch("src.pipeline.orchestrator.stage2_analyst", return_value=MOCK_STAGE2)
@patch("src.pipeline.orchestrator.stage1_scanner", return_value=MOCK_STAGE1)
@patch("src.pipeline.orchestrator.stage0_orchestrator", return_value=MOCK_STAGE0)
def test_pii_in_material_detected(s0, s1, s2, s4, s5):
    result = orchestrator.run_pipeline(
        "def foo(): pass\n# user@example.com",
        "pii.py",
        verbose=False,
    )
    audit = result["audit"]
    assert audit["pii_detected"] is True
    assert audit["critique_verdict"] in ("REQUIRES_REVIEW", "NEEDS_VERIFICATION")


@patch("src.pipeline.orchestrator.stage5_transmitter", return_value=MOCK_STAGE5)
@patch("src.pipeline.orchestrator.stage4_synthesizer", return_value=MOCK_STAGE4)
@patch("src.pipeline.orchestrator.stage2_analyst", return_value=MOCK_STAGE2)
@patch("src.pipeline.orchestrator.stage1_scanner", return_value=MOCK_STAGE1)
@patch("src.pipeline.orchestrator.stage0_orchestrator", return_value=MOCK_STAGE0)
def test_final_markdown_has_audit_trail(s0, s1, s2, s4, s5):
    result = orchestrator.run_pipeline("def foo(): pass", "a.py", verbose=False)
    md = result["final_markdown"]
    assert "[AUDIT_TRAIL]" in md
    assert "[COMPLETENESS]" in md


# === Extended pipeline scenarios ===

MOCK_STAGE0_EMERGENCY = {
    "level": "D0",
    "route": [],
    "research_first": False,
    "subst_count": 0,
    "flags": ["EMERGENCY_INTERRUPT"],
    "_meta": {"tokens_in": 10, "tokens_out": 5},
}


@patch("src.pipeline.orchestrator.stage0_orchestrator", return_value=MOCK_STAGE0_EMERGENCY)
def test_emergency_interrupt_returns_early(s0):
    result = orchestrator.run_pipeline("secret = 'hardcoded_secret_12345'", "s.py", verbose=False)
    assert result.get("emergency") is True
    assert "audit" in result
    assert "[AUDIT_TRAIL]" in result["final_markdown"]


@patch("src.pipeline.orchestrator.stage5_transmitter", return_value=MOCK_STAGE5)
@patch("src.pipeline.orchestrator.stage4_synthesizer", return_value=MOCK_STAGE4)
@patch("src.pipeline.orchestrator.stage2_analyst", return_value=MOCK_STAGE2)
@patch("src.pipeline.orchestrator.stage1_scanner", return_value=MOCK_STAGE1)
@patch("src.pipeline.orchestrator.stage0_orchestrator", return_value=MOCK_STAGE0)
def test_result_has_all_stages(s0, s1, s2, s4, s5):
    result = orchestrator.run_pipeline("def foo(): pass", "a.py", verbose=False)
    assert "stage0" in result
    assert "stage1" in result
    assert "stage2" in result
    assert "stage4" in result


@patch("src.pipeline.orchestrator.stage5_transmitter", return_value=MOCK_STAGE5)
@patch("src.pipeline.orchestrator.stage4_synthesizer", return_value=MOCK_STAGE4)
@patch("src.pipeline.orchestrator.stage2_analyst", return_value=MOCK_STAGE2)
@patch("src.pipeline.orchestrator.stage1_scanner", return_value=MOCK_STAGE1)
@patch("src.pipeline.orchestrator.stage0_orchestrator", return_value=MOCK_STAGE0)
def test_material_hash_in_result(s0, s1, s2, s4, s5):
    result = orchestrator.run_pipeline("def foo(): pass", "a.py", verbose=False)
    h = result["audit"]["material_hash"]
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64
