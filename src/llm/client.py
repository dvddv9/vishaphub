# -*- coding: utf-8 -*-
"""Unified LLM entry point (v7.2).

Providers: custom (OpenAI-compatible).
Selection: always custom (endpoint-only, v7.3.5).

DeepSeek is reachable via custom: CUSTOM_LLM_URL=https://api.deepseek.com/v1.
"""
from __future__ import annotations

from contextvars import ContextVar

from src.llm._observe import observe_llm_result


_api_key_var: ContextVar[str | None] = ContextVar("llm_api_key", default=None)


def set_api_key(key: str | None) -> None:
    _api_key_var.set(key)


def get_api_key() -> str | None:
    return _api_key_var.get()


NO_CUSTOM_TEXT = (
    "[LLM error] custom provider failed: set CUSTOM_LLM_URL / CUSTOM_LLM_KEY / CUSTOM_LLM_MODEL."
)


def _resolve_provider() -> str:
    """v7.3.16: provider selection (DeepSeek API is default)."""
    import os
    mode = os.getenv("VISHAP_LLM_PROVIDER", "custom").strip().lower()
    if mode in ("custom", "openai", "groq", "ollama", "anthropic", "android"):
        return "custom"
    if mode == "auto":
        if os.getenv("CUSTOM_LLM_URL", "").strip() and os.getenv("CUSTOM_LLM_KEY", "").strip():
            return "custom"
        return "custom"
    return "custom"


def _chat_custom(system: str, user: str, temperature: float, max_tokens: int, api_key: str | None = None) -> dict:
    try:
        from src.llm.custom_client import CustomClient
        api_key = api_key or get_api_key()
        c = CustomClient(api_key=api_key)
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
         max_tokens: int = 2000,
         api_key: str | None = None) -> dict:
    return _chat_custom(system, user, temperature, max_tokens, api_key=api_key)