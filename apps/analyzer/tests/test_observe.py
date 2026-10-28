# -*- coding: utf-8 -*-
"""Tests for src/llm/_observe.py (v6.1 Block 4)."""
from unittest.mock import patch

from src.llm._observe import observe_llm_result


def test_observe_success_increments_request():
    result = {"model": "deepseek-chat", "tokens_in": 10, "tokens_out": 20}
    with patch("src.llm._observe.observe_llm_request") as req, \
         patch("src.llm._observe.observe_llm_tokens"):
        observe_llm_result(result)
    req.assert_called_once_with("deepseek-chat", "success")


def test_observe_success_increments_tokens():
    result = {"model": "deepseek-chat", "tokens_in": 10, "tokens_out": 20}
    with patch("src.llm._observe.observe_llm_request"), \
         patch("src.llm._observe.observe_llm_tokens") as tok:
        observe_llm_result(result)
    assert tok.call_count == 2
    tok.assert_any_call("deepseek-chat", "prompt", 10)
    tok.assert_any_call("deepseek-chat", "completion", 20)


def test_observe_error_skips_tokens():
    result = {"model": "deepseek-chat", "tokens_in": 10, "tokens_out": 20}
    with patch("src.llm._observe.observe_llm_request") as req, \
         patch("src.llm._observe.observe_llm_tokens") as tok:
        observe_llm_result(result, status="error")
    req.assert_called_once_with("deepseek-chat", "error")
    tok.assert_not_called()


def test_observe_handles_missing_model():
    result = {"tokens_in": 1, "tokens_out": 2}
    with patch("src.llm._observe.observe_llm_request") as req, \
         patch("src.llm._observe.observe_llm_tokens"):
        observe_llm_result(result)
    req.assert_called_once_with("unknown", "success")


def test_observe_handles_none_tokens():
    result = {"model": "m", "tokens_in": None, "tokens_out": None}
    with patch("src.llm._observe.observe_llm_request"), \
         patch("src.llm._observe.observe_llm_tokens") as tok:
        observe_llm_result(result)
    tok.assert_any_call("m", "prompt", 0)
    tok.assert_any_call("m", "completion", 0)


def test_observe_returns_result_unchanged():
    result = {"model": "m", "tokens_in": 1, "tokens_out": 2}
    with patch("src.llm._observe.observe_llm_request"), \
         patch("src.llm._observe.observe_llm_tokens"):
        out = observe_llm_result(result)
    assert out is result
