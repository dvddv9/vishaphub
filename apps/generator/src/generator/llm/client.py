"""The one entry point for a model call.

The analog of Vishap's `llm/client.py`: callers use `chat()` and do not care which provider is behind it.
Today there is one, the custom OpenAI-compatible one (`custom_client.py`).
"""

from __future__ import annotations

from generator.llm._observe import observe_llm_result
from generator.llm.custom_client import CustomClient, CustomError, LLMConfig

LLMError = CustomError


def chat(messages: list[dict], config: LLMConfig | None = None, max_tokens: int = 4096) -> str:
    """Send one chat request and return the text of the first choice."""
    done = CustomClient(config).complete(messages, max_tokens)
    observe_llm_result(messages, done.text, done.tokens_in, done.tokens_out)
    return done.text
