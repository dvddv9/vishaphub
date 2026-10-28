# -*- coding: utf-8 -*-
"""LLM layer: custom (OpenAI-compatible / DSH endpoint) is the only provider (v7.3.5).

There is no direct DeepSeek / OpenAI / OpenAI-compatible call any more, so these
tests pin the new contract: one provider, one call path, one error shape.

The provider is configured via CUSTOM_LLM_* env vars; `temperature` / `max_tokens` are accepted by
`chat()` for interface compatibility but are not forwarded.
"""

from src.llm import client



def test_resolve_provider_auto(monkeypatch):
    # An old .env value must not resurrect a removed provider.
    monkeypatch.setenv("VISHAP_LLM_PROVIDER", "auto")
    # v7.3.5: endpoint-only, always "custom"
    assert client._resolve_provider() == "custom"





def test_env_example_documents_custom_vars():
    """v7.3.5: only custom (endpoint) is documented."""
    from pathlib import Path
    content = Path(".env.example").read_text(encoding="utf-8")
    assert "CUSTOM_LLM_URL" in content
    assert "CUSTOM_LLM_KEY" in content
    assert "CUSTOM_LLM_MODEL" in content
    assert "DEEPSEEK_API_KEY" not in content
    assert "HARNESS_URL" not in content
    assert "HARNESS_TOKEN" not in content


def test_mode_is_custom_only():
    """custom stays the default; the provider list is pinned so adding or
    removing a provider without updating the docs/tests fails loudly."""
    from src.storage.mode import DEFAULT_MODE, VALID_MODES
    assert DEFAULT_MODE == "custom"
    assert VALID_MODES == ("custom", "openai", "groq", "ollama", "anthropic", "android")

