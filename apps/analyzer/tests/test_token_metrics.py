# -*- coding: utf-8 -*-
"""Tests for LLM token/request metrics (v6.1 Block 4)."""
import pytest
from fastapi.testclient import TestClient

from src.observability import metrics


def _val(name, labels):
    return metrics.get_sample_value(name, labels)


@pytest.fixture
def client():
    from src.main import app
    return TestClient(app)


def test_llm_tokens_counter_increments():
    labels = {"model": "deepseek-chat", "type": "prompt"}
    before = _val("vishap_llm_tokens_total", labels)
    metrics.observe_llm_tokens("deepseek-chat", "prompt", 100)
    assert _val("vishap_llm_tokens_total", labels) == before + 100


def test_llm_tokens_completion():
    labels = {"model": "deepseek-chat", "type": "completion"}
    before = _val("vishap_llm_tokens_total", labels)
    metrics.observe_llm_tokens("deepseek-chat", "completion", 200)
    assert _val("vishap_llm_tokens_total", labels) == before + 200


def test_llm_requests_counter_success():
    labels = {"model": "deepseek-chat", "status": "success"}
    before = _val("vishap_llm_requests_total", labels)
    metrics.observe_llm_request("deepseek-chat", "success")
    assert _val("vishap_llm_requests_total", labels) == before + 1


def test_llm_requests_counter_error():
    labels = {"model": "deepseek-chat", "status": "error"}
    before = _val("vishap_llm_requests_total", labels)
    metrics.observe_llm_request("deepseek-chat", "error")
    assert _val("vishap_llm_requests_total", labels) == before + 1


def test_tokens_by_model():
    m1 = {"model": "gpt-4o-mini", "type": "prompt"}
    m2 = {"model": "qwen2.5:7b", "type": "prompt"}
    b1 = _val("vishap_llm_tokens_total", m1)
    b2 = _val("vishap_llm_tokens_total", m2)
    metrics.observe_llm_tokens("gpt-4o-mini", "prompt", 10)
    metrics.observe_llm_tokens("qwen2.5:7b", "prompt", 20)
    assert _val("vishap_llm_tokens_total", m1) == b1 + 10
    assert _val("vishap_llm_tokens_total", m2) == b2 + 20


def test_tokens_appear_in_metrics_output(client):
    body = client.get("/metrics").text
    assert "vishap_llm_tokens_total" in body
    assert "vishap_llm_requests_total" in body
