# -*- coding: utf-8 -*-
"""LLM result observation helper (v6.1 Block 4).

Shared by the sync (client.py) and async (async_client.py) LLM clients so the
token/request metric logic lives in one place.
"""
from src.observability.metrics import observe_llm_request, observe_llm_tokens


def observe_llm_result(result: dict, status: str = "success") -> dict:
    """Record LLM request/token metrics and return the result unchanged."""
    model = result.get("model", "unknown") or "unknown"
    observe_llm_request(model, status)
    if status == "success":
        observe_llm_tokens(model, "prompt", result.get("tokens_in", 0) or 0)
        observe_llm_tokens(model, "completion", result.get("tokens_out", 0) or 0)
    return result
