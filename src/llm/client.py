# -*- coding: utf-8 -*-
"""Unified LLM entry point (v7.2).

Providers: custom (OpenAI-compatible).
Selection: always custom (endpoint-only, v7.3.5).

DeepSeek is reachable via custom: CUSTOM_LLM_URL=https://api.deepseek.com/v1.
"""
from __future__ import annotations


from src.llm._observe import observe_llm_result


NO_CUSTOM_TEXT = (
    "[LLM error] custom provider failed: set CUSTOM_LLM_URL / CUSTOM_LLM_KEY / CUSTOM_LLM_MODEL."
)


def _resolve_provider() -> str:
    """v7.3.16: provider selection (DeepSeek API is default).

    Priority:
      1. explicit VISHAP_LLM_PROVIDER (custom | openai | groq | ollama | anthropic | android | auto)
      2. auto -> custom if CUSTOM_LLM_URL set, else custom
      3. default: custom (DeepSeek API: https://api.deepseek.com/v1)
    """
    import os
    mode = os.getenv("VISHAP_LLM_PROVIDER", "custom").strip().lower()
    if mode in ("custom", "openai", "groq", "ollama", "anthropic", "android"):
        # all map to custom (OpenAI-compatible endpoint)
        return "custom"
    if mode == "auto":
        if os.getenv("CUSTOM_LLM_URL", "").strip() and os.getenv("CUSTOM_LLM_KEY", "").strip():
            return "custom"
        return "custom"
    return "custom"


def _chat_custom(system: str, user: str, temperature: float, max_tokens: int) -> dict:
    try:
        from src.llm.custom_client import CustomClient
        c = CustomClient()
        try:
            result = c.chat(user, system, temperature=temperature, max_tokens=max_tokens)
        finally:
            c.close()
        return observe_llm_result(result)
    except Exception as e:
        return observe_llm_result({
            "text": f"{NO_CUSTOM_TEXT} ({e})",
            "tokens_in": 0, "tokens_out": 0,
            "model": "none", "mode": "error",
        }, status="error")



def chat(system: str, user: str,
         temperature: float = 0.0,
         max_tokens: int = 2000) -> dict:
    provider = _resolve_provider()
    if provider == "custom":
        return _chat_custom(system, user, temperature, max_tokens)
    return {"text": "[LLM error] custom provider failed", "tokens_in": 0, "tokens_out": 0, "model": "none", "mode": "error"}


def current_provider() -> str:
    return _resolve_provider()
