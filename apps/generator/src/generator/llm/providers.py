"""Allow-listed LLM providers for requests that bring their own key.

The analog of Vishap's `llm/providers.py`.

SECURITY: the base URL is NEVER taken from a request. A caller picks a provider *id*; the URL comes from this
table, on the server. Accepting a URL from the browser would let a page make the server send a key (yours,
or the caller's) to any host, or call addresses inside your network (SSRF).

`GENERATOR_ALLOWED_PROVIDERS=anthropic,deepseek` narrows the list (default: all). The local model (Ollama) is
offered only when the server is on loopback, or when the operator sets `GENERATOR_ENABLE_LOCAL_PROVIDER=1`;
its address comes from `OLLAMA_URL` / `OLLAMA_MODEL` on the server. A custom endpoint is configured only
through the server's own CUSTOM_LLM_* variables.
"""

from __future__ import annotations

import os
import re

from generator.llm.custom_client import LLMConfig, LLMConfigError, config_from_env

# id -> (label, OpenAI-compatible base URL, default model)
PRESETS: dict[str, tuple[str, str, str]] = {
    "anthropic": ("Anthropic (Claude)", "https://api.anthropic.com/v1", "claude-sonnet-5-5"),
    "deepseek": ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    "groq": ("Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "openai": ("OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat"),
}
LOCAL_ID = "ollama"
SERVER_ID = "server"       # "use the model the server is configured with"

_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,99}$")


class ProviderError(ValueError):
    """Unknown or disabled provider, or a malformed model name."""


def local_enabled(loopback: bool = False) -> bool:
    return loopback or os.getenv("GENERATOR_ENABLE_LOCAL_PROVIDER", "").strip().lower() in ("1", "true", "yes", "on")


def _presets(loopback: bool) -> dict[str, tuple[str, str, str]]:
    presets = dict(PRESETS)
    if local_enabled(loopback):
        presets[LOCAL_ID] = ("Local model (Ollama)",
                             os.getenv("OLLAMA_URL", "").strip() or "http://127.0.0.1:11434/v1",
                             os.getenv("OLLAMA_MODEL", "").strip() or "llama3")
    return presets


def allowed_ids(loopback: bool = False) -> list[str]:
    presets = _presets(loopback)
    raw = os.getenv("GENERATOR_ALLOWED_PROVIDERS", "").strip()
    if not raw:
        return list(presets)
    wanted = {p.strip().lower() for p in raw.split(",") if p.strip()}
    return [p for p in presets if p in wanted]


def list_providers(loopback: bool = False) -> list[dict]:
    presets = _presets(loopback)
    return [{"id": pid, "label": presets[pid][0], "default_model": presets[pid][2],
             "needs_key": pid != LOCAL_ID} for pid in allowed_ids(loopback)]


def resolve(provider: str | None, model: str | None, loopback: bool = False) -> tuple[str, str] | None:
    """(base_url, model) for an allowed provider id; None means "the server's own model"."""
    pid = (provider or "").strip().lower()
    if not pid or pid == SERVER_ID:
        return None
    presets = _presets(loopback)
    if pid not in presets or pid not in allowed_ids(loopback):
        raise ProviderError(f"unknown or disabled provider: {pid[:40]!r}")
    chosen = (model or "").strip() or presets[pid][2]
    if not _MODEL_RE.match(chosen):
        raise ProviderError("invalid model name")
    return presets[pid][1], chosen


def config_for(provider: str | None, model: str | None, key: str = "", thinking: str = "",
               loopback: bool = False) -> LLMConfig | None:
    """The settings for a request that names a provider; None for the server's own model."""
    target = resolve(provider, model, loopback)
    if target is None:
        return None
    url, chosen = target
    env = {"CUSTOM_LLM_URL": url, "CUSTOM_LLM_MODEL": chosen, "CUSTOM_LLM_KEY": key or "",
           "CUSTOM_LLM_THINKING": thinking or ""}
    return config_from_env(env)


__all__ = ["LLMConfigError", "LOCAL_ID", "PRESETS", "ProviderError", "SERVER_ID", "allowed_ids",
           "config_for", "list_providers", "resolve"]
