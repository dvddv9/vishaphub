# -*- coding: utf-8 -*-
"""Allow-listed LLM providers for bring-your-own-key requests.

SECURITY: the base URL is NEVER taken from a request. A caller picks a provider
*id*; the URL comes from this table (server-side). Accepting a caller-supplied
URL would let anyone make the server send their key (or, worse, the operator's
key) to an arbitrary host (SSRF / key exfiltration).

``VISHAP_ALLOWED_PROVIDERS=anthropic,deepseek`` narrows the list (default: all).
"""
from __future__ import annotations

import os
import re

# id -> (label, OpenAI-compatible base URL, default model)
PRESETS: dict[str, tuple[str, str, str]] = {
    "anthropic": ("Anthropic (Claude)", "https://api.anthropic.com/v1", "claude-sonnet-5-5"),
    "groq": ("Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "deepseek": ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    "openai": ("OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat"),
}

# Local model (Ollama). Not part of PRESETS: its address is the *server's own*
# loopback, so offering it on a public deployment would let any visitor make the
# server call its own localhost (SSRF) and could never reach the visitor's machine.
# It is listed only when the operator opts in with VISHAP_ENABLE_LOCAL_PROVIDER=1
# (run Vishap on your own machine). The address and model come from OLLAMA_URL /
# OLLAMA_MODEL on the server, never from a request. No API key is needed.
LOCAL_ID = "ollama"

# Pseudo-provider for "analysis without LLM": the built-in rule engine only. It is
# not a provider (no URL, no key) and costs the operator nothing, so any caller may
# pick it, even on a server-key-only deployment.
RULES_ID = "rules"


def is_rules_only(provider: str | None) -> bool:
    return (provider or "").strip().lower() == RULES_ID


def local_enabled() -> bool:
    return os.getenv("VISHAP_ENABLE_LOCAL_PROVIDER", "").strip().lower() in ("1", "true", "yes", "on")


def _presets() -> dict[str, tuple[str, str, str]]:
    presets = dict(PRESETS)
    if local_enabled():
        presets[LOCAL_ID] = (
            "Local model (Ollama)",
            os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/v1").strip() or "http://127.0.0.1:11434/v1",
            os.getenv("OLLAMA_MODEL", "llama3").strip() or "llama3",
        )
    return presets

_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,99}$")


class ProviderError(ValueError):
    """Unknown/disallowed provider or malformed model name."""


def allowed_ids() -> list[str]:
    presets = _presets()
    raw = os.getenv("VISHAP_ALLOWED_PROVIDERS", "").strip()
    if not raw:
        return list(presets)
    wanted = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return [p for p in presets if p in wanted]


def list_providers() -> list[dict]:
    return [
        {"id": pid, "label": _presets()[pid][0], "default_model": _presets()[pid][2],
         "needs_key": pid != LOCAL_ID}
        for pid in allowed_ids()
    ]


def resolve(provider: str | None, model: str | None) -> tuple[str, str] | None:
    """Return (base_url, model) for an allowed provider id, or None for the server default."""
    pid = (provider or "").strip().lower()
    if not pid:
        return None
    presets = _presets()
    if pid not in presets or pid not in allowed_ids():
        raise ProviderError(f"Unknown or disabled LLM provider: {pid[:40]!r}")
    chosen = (model or "").strip() or presets[pid][2]
    if not _MODEL_RE.match(chosen):
        raise ProviderError("Invalid model name.")
    return presets[pid][1], chosen
