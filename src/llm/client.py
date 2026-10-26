# -*- coding: utf-8 -*-
"""Unified LLM entry point (v7.2).

Providers: custom (OpenAI-compatible).
Selection: always custom (endpoint-only, v7.3.5).

DeepSeek is reachable via custom: CUSTOM_LLM_URL=https://api.deepseek.com/v1.
"""
from __future__ import annotations

from contextvars import ContextVar

from src.llm._observe import observe_llm_result
from src.llm._scrub import scrub


_api_key_var: ContextVar[str | None] = ContextVar("llm_api_key", default=None)


def set_api_key(key: str | None) -> None:
    _api_key_var.set(key)


def get_api_key() -> str | None:
    return _api_key_var.get()


# (base_url, model) chosen by the caller from the server's provider allow-list
_target_var: ContextVar[tuple[str, str] | None] = ContextVar("llm_target", default=None)


def set_llm_target(target: tuple[str, str] | None) -> None:
    _target_var.set(target)


def get_llm_target() -> tuple[str, str] | None:
    return _target_var.get()


def server_key_only() -> bool:
    """True when the server's own key (DeepSeek by default) is the ONLY LLM source.

    VISHAP_SERVER_KEY_ONLY=1: callers cannot choose another provider/model or send
    their own key -- any X-LLM-* headers are ignored. Takes precedence over
    VISHAP_REQUIRE_USER_LLM_KEY.
    """
    import os
    return os.getenv("VISHAP_SERVER_KEY_ONLY", "").strip().lower() in ("1", "true", "yes", "on")


def server_has_key() -> bool:
    import os
    return bool(os.getenv("CUSTOM_LLM_KEY", "").strip())


def require_user_key() -> bool:
    """True when the operator forbids falling back to the server's own LLM key.

    VISHAP_REQUIRE_USER_LLM_KEY=1 (public/demo deploys): every analysis must carry
    the caller's own key (``X-LLM-Api-Key``), so the operator's key is never spent.
    """
    import os
    if server_key_only():
        return False
    return os.getenv("VISHAP_REQUIRE_USER_LLM_KEY", "").strip().lower() in ("1", "true", "yes", "on")


USER_KEY_REQUIRED_TEXT = (
    "[LLM error] this server does not use its own LLM key: send yours in the "
    "X-LLM-Api-Key header (or enter it in the UI)."
)


NO_CUSTOM_TEXT = (
    "[LLM error] custom provider failed: check the provider, model and API key."
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


PROVIDER_NEEDS_KEY_TEXT = (
    "[LLM error] a chosen LLM provider needs your own key (X-LLM-Api-Key); "
    "the server's key is never sent to another provider."
)


def _chat_custom(system: str, user: str, temperature: float, max_tokens: int,
                 api_key: str | None = None,
                 target: tuple[str, str] | None = None) -> dict:
    try:
        from src.llm.custom_client import CustomClient
        api_key = api_key or get_api_key()
        target = target or get_llm_target()
        if target and not api_key:
            # operator key must never travel to a caller-chosen provider
            return observe_llm_result({
                "text": PROVIDER_NEEDS_KEY_TEXT,
                "tokens_in": 0, "tokens_out": 0,
                "model": "none", "mode": "error",
            }, status="error")
        if require_user_key() and not api_key:
            # never fall back to CUSTOM_LLM_KEY from the environment
            return observe_llm_result({
                "text": USER_KEY_REQUIRED_TEXT,
                "tokens_in": 0, "tokens_out": 0,
                "model": "none", "mode": "error",
            }, status="error")
        c = CustomClient(base_url=target[0] if target else None,
                         api_key=api_key,
                         model=target[1] if target else None)
        try:
            result = c.chat(user, system, temperature=temperature, max_tokens=max_tokens)
        finally:
            c.close()
        return observe_llm_result(result)
    except Exception as e:
        return observe_llm_result({
            "text": f"{NO_CUSTOM_TEXT} ({scrub(e, api_key)})",
            "tokens_in": 0, "tokens_out": 0,
            "model": "none", "mode": "error",
        }, status="error")


def chat(system: str, user: str,
         temperature: float = 0.0,
         max_tokens: int = 2000,
         api_key: str | None = None) -> dict:
    return _chat_custom(system, user, temperature, max_tokens, api_key=api_key)