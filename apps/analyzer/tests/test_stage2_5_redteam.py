# -*- coding: utf-8 -*-
"""Tests for stage2_5_redteam (v7.3.11 self-adversarial)."""
from unittest.mock import patch



def test_redteam_skipped_by_default(monkeypatch):
    monkeypatch.delenv("VISHAP_REDTEAM", raising=False)
    from src.pipeline.stages import stage2_5_redteam
    result = stage2_5_redteam("def f(): pass", {"stage2": {}})
    assert result["missed"] == []
    assert result["mode"] == "skipped"


def test_redteam_finds_missed(monkeypatch):
    monkeypatch.setenv("VISHAP_REDTEAM", "1")
    monkeypatch.setattr(
        "src.pipeline.stages.chat" if hasattr(__import__("src.pipeline.stages", fromlist=["chat"]), "chat") else "src.llm.client.chat",
        lambda *a, **kw: {"text": '{"missed": [{"cwe": "CWE-89", "reason": "SQLi", "severity": "critical"}], "critique": "ok"}', "tokens_in": 10, "tokens_out": 20, "mode": "custom"},
        raising=False,
    )
    # fallback: patch directly on src.llm.client.chat (stage2_5_redteam imports it inside function)
    with patch("src.llm.client.chat") as mock_chat:
        mock_chat.return_value = {
            "text": '{"missed": [{"cwe": "CWE-89", "reason": "SQLi", "severity": "critical"}], "critique": "ok"}',
            "tokens_in": 10, "tokens_out": 20, "mode": "custom",
        }
        from src.pipeline.stages import stage2_5_redteam
        result = stage2_5_redteam("def f(): pass", {"stage2": {"risk_nodes": []}})
    assert result["mode"] == "custom"
    assert len(result["missed"]) == 1
    assert result["missed"][0]["cwe"] == "CWE-89"


def test_redteam_duplicate_filtered(monkeypatch):
    """Red team finds CWE-89, but Analyst already has it — merge filters it."""
    monkeypatch.setenv("VISHAP_REDTEAM", "1")
    stage2 = {"risk_nodes": [{"cwe": "CWE-89", "reason": "existing"}]}
    stage2_5 = {"missed": [{"cwe": "CWE-89", "reason": "dup", "severity": "critical"}]}
    existing = {r.get("cwe") for r in stage2["risk_nodes"] if isinstance(r, dict)}
    new = [m for m in stage2_5["missed"] if m.get("cwe") not in existing]
    assert len(new) == 0


def test_redteam_handles_llm_error(monkeypatch):
    monkeypatch.setenv("VISHAP_REDTEAM", "1")
    with patch("src.llm.client.chat", side_effect=RuntimeError("boom")):
        from src.pipeline.stages import stage2_5_redteam
        result = stage2_5_redteam("x", {"stage2": {}})
    assert result["mode"] == "error"
    assert result["missed"] == []
