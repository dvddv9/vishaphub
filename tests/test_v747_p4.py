# -*- coding: utf-8 -*-
"""Provider list order and the opt-in local (Ollama) provider."""
import pytest

from src.llm import providers


def test_default_order_is_claude_groq_deepseek_then_the_rest(monkeypatch):
    monkeypatch.delenv("VISHAP_ALLOWED_PROVIDERS", raising=False)
    monkeypatch.delenv("VISHAP_ENABLE_LOCAL_PROVIDER", raising=False)
    assert providers.allowed_ids() == ["anthropic", "groq", "deepseek", "openai", "openrouter"]


def test_local_provider_is_off_by_default(monkeypatch):
    monkeypatch.delenv("VISHAP_ENABLE_LOCAL_PROVIDER", raising=False)
    monkeypatch.delenv("VISHAP_ALLOWED_PROVIDERS", raising=False)
    assert "ollama" not in providers.allowed_ids()
    with pytest.raises(providers.ProviderError):
        providers.resolve("ollama", None)


def test_local_provider_listed_last_and_needs_no_key_when_enabled(monkeypatch):
    monkeypatch.setenv("VISHAP_ENABLE_LOCAL_PROVIDER", "1")
    monkeypatch.delenv("VISHAP_ALLOWED_PROVIDERS", raising=False)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    listed = providers.list_providers()
    assert [p["id"] for p in listed][-1] == "ollama"
    assert {p["id"]: p["needs_key"] for p in listed}["ollama"] is False
    assert all(p["needs_key"] for p in listed if p["id"] != "ollama")
    assert providers.resolve("ollama", None) == ("http://127.0.0.1:11434/v1", "llama3")


def test_local_address_comes_from_the_server_env_never_the_request(monkeypatch):
    monkeypatch.setenv("VISHAP_ENABLE_LOCAL_PROVIDER", "1")
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9999/v1")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5")
    assert providers.resolve("ollama", None) == ("http://127.0.0.1:9999/v1", "qwen2.5")
    assert providers.resolve("ollama", "llama3.2") == ("http://127.0.0.1:9999/v1", "llama3.2")
    with pytest.raises(providers.ProviderError):
        providers.resolve("http://127.0.0.1:11434/v1", None)


def test_allowed_providers_env_can_hide_the_local_provider(monkeypatch):
    monkeypatch.setenv("VISHAP_ENABLE_LOCAL_PROVIDER", "1")
    monkeypatch.setenv("VISHAP_ALLOWED_PROVIDERS", "anthropic")
    assert providers.allowed_ids() == ["anthropic"]
