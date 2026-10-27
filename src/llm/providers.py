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
    "deepseek": ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    "openai": ("OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    "groq": ("Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat"),
}

_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,99}$")


class ProviderError(ValueError):
    """Unknown/disallowed provider or malformed model name."""


def allowed_ids() -> list[str]:
    raw = os.getenv("VISHAP_ALLOWED_PROVIDERS", "").strip()
    if not raw:
        return list(PRESETS)
    wanted = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return [p for p in PRESETS if p in wanted]


def list_providers() -> list[dict]:
    return [
        {"id": pid, "label": PRESETS[pid][0], "default_model": PRESETS[pid][2]}
        for pid in allowed_ids()
    ]


def resolve(provider: str | None, model: str | None) -> tuple[str, str] | None:
    """Return (base_url, model) for an allowed provider id, or None for the server default."""
    pid = (provider or "").strip().lower()
    if not pid:
        return None
    if pid not in PRESETS or pid not in allowed_ids():
        raise ProviderError(f"Unknown or disabled LLM provider: {pid[:40]!r}")
    chosen = (model or "").strip() or PRESETS[pid][2]
    if not _MODEL_RE.match(chosen):
        raise ProviderError("Invalid model name.")
    return PRESETS[pid][1], chosen
