# -*- coding: utf-8 -*-
"""OpenAI-compatible custom provider (Groq / OpenAI / DeepSeek via custom)."""
from __future__ import annotations

import os
import json  # noqa: F401  # (if needed)

# v7.3.1: Claude 5.x deprecates `temperature` (HTTP 400).
# Set CUSTOM_LLM_SEND_TEMPERATURE=false for Claude 5.x.
SEND_TEMPERATURE = os.getenv("CUSTOM_LLM_SEND_TEMPERATURE", "true").lower() == "true"

# Endpoint+model pairs that rejected a parameter (HTTP 400): remembered so the
# next call does not pay for a failed round trip. Providers differ per model, so
# this is learned at runtime instead of hard-coded.
_NO_TEMPERATURE: set[tuple[str, str]] = set()
_USE_MAX_COMPLETION_TOKENS: set[tuple[str, str]] = set()

import requests
from dotenv import load_dotenv

load_dotenv()

from src.storage.settings import get_settings

def _cfg(key: str, default: str = "") -> str:
    """settings.json (runtime) wins over .env (defaults)."""
    try:
        v = get_settings().get(key)
        if v:
            return str(v)
    except Exception:
        pass
    return os.getenv(key, default)
DEFAULT_URL = _cfg("CUSTOM_LLM_URL", "")
DEFAULT_KEY = _cfg("CUSTOM_LLM_KEY", "")
DEFAULT_MODEL = _cfg("CUSTOM_LLM_MODEL", "")
DEFAULT_TIMEOUT = float(os.getenv("CUSTOM_LLM_TIMEOUT", "120"))


class CustomError(RuntimeError):
    """Any error talking to the custom OpenAI-compatible endpoint."""


class CustomClient:
    def __init__(self, base_url: str | None = None,
                 api_key: str | None = None,
                 model: str | None = None,
                 timeout: float | None = None) -> None:
        self.base_url = (base_url or _cfg("CUSTOM_LLM_URL", DEFAULT_URL)).rstrip("/")
        self.api_key  = api_key  or _cfg("CUSTOM_LLM_KEY", DEFAULT_KEY)
        self.model    = model    or _cfg("CUSTOM_LLM_MODEL", DEFAULT_MODEL)
        self.timeout  = timeout  or DEFAULT_TIMEOUT
        if not self.base_url:
            raise CustomError("CUSTOM_LLM_URL is empty")
        if not self.api_key:
            raise CustomError("CUSTOM_LLM_KEY is empty")
        if not self.model:
            raise CustomError("CUSTOM_LLM_MODEL is empty")

    def chat(self, user: str, system: str = "",
             temperature: float = 0.0, max_tokens: int = 2000) -> dict:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        route = (self.base_url, self.model)
        payload = {
            "model": self.model,
            "messages": messages,
            # v7.3.1: skip temperature if CUSTOM_LLM_SEND_TEMPERATURE=false
            **({"temperature": temperature} if SEND_TEMPERATURE and route not in _NO_TEMPERATURE else {}),
            "stream": False,
        }
        payload["max_completion_tokens" if route in _USE_MAX_COMPLETION_TOKENS else "max_tokens"] = max_tokens
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        def _post(body: dict):
            return requests.post(
                f"{self.base_url}/chat/completions",
                headers={**headers, "Content-Type": "application/json; charset=utf-8"},
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                timeout=self.timeout,
            )

        try:
            r = _post(payload)
            # Some models reject parameters other models require
            # ("`temperature` is deprecated for this model", "use max_completion_tokens").
            # Retry once without/with the offending parameter and remember it.
            if r.status_code == 400:
                low = r.text.lower()
                retry = dict(payload)
                if "temperature" in low and "temperature" in retry:
                    retry.pop("temperature")
                    _NO_TEMPERATURE.add(route)
                    r = _post(retry)
                    low = r.text.lower() if r.status_code == 400 else ""
                if r.status_code == 400 and "max_completion_tokens" in low and "max_tokens" in retry:
                    retry["max_completion_tokens"] = retry.pop("max_tokens")
                    _USE_MAX_COMPLETION_TOKENS.add(route)
                    r = _post(retry)
        except requests.RequestException as e:
            raise CustomError(f"custom request failed: {e}") from e
        if r.status_code != 200:
            raise CustomError(f"custom HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        try:
            msg = data["choices"][0]["message"]
            text = msg.get("content") or ""
            if not text:
                # reasoning models (deepseek-flash / v4) put text in reasoning_content
                text = msg.get("reasoning_content") or ""
        except (KeyError, IndexError) as e:
            raise CustomError(f"unexpected custom response: {e}") from e
        usage = data.get("usage") or {}
        return {
            "text": text,
            "tokens_in": int(usage.get("prompt_tokens", 0) or 0),
            "tokens_out": int(usage.get("completion_tokens", 0) or 0),
            "model": data.get("model", self.model),
            "mode": "custom",
        }

    def close(self) -> None:
        pass


# backward compat
CustomLLMClient = CustomClient
