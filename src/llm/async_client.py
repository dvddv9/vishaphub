# -*- coding: utf-8 -*-
"""Async LLM entry point — custom (OpenAI-compatible) only.

The custom client is synchronous (HTTP + polling a session log), so it runs in a
worker thread. This is the async twin of `src.llm.client.chat`: same configuration,
same error contract.
"""
import asyncio

from src.llm._observe import observe_llm_result


async def async_chat(system: str, user: str,
                     temperature: float = 0.0,
                     max_tokens: int = 2000) -> dict:
    """Async LLM entry point — custom (OpenAI-compatible).

    Mirrors `src.llm.client.chat`: provider is resolved via
    `_resolve_provider()` (always custom in v7.3.5).
    """
    from src.llm.client import _resolve_provider, _chat_custom
    provider = _resolve_provider()
    loop = asyncio.get_event_loop()

    if provider == "custom":
        return await loop.run_in_executor(
            None, lambda: _chat_custom(system, user, temperature, max_tokens),
        )

    try:
        result = await loop.run_in_executor(None, lambda: h.chat(user, system))
        return observe_llm_result(result)
    except Exception as e:
        return observe_llm_result({
            "text": f"[LLM error] custom provider failed ({e})",
            "tokens_in": 0, "tokens_out": 0,
            "model": "none", "mode": "error",
        }, status="error")
