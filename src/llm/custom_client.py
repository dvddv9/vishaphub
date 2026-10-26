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
# Output-token ceilings learned from "max_tokens must be <= N" 400s (e.g. deepseek-chat: 8192).
_MAX_OUT_CAP: dict[tuple[str, str], int] = {}

import re as _re
import time as _time

_CAP_RES = (
    _re.compile(r"\[\s*1\s*,\s*(\d{3,7})\s*\]"),
    _re.compile(r"(?:at most|maximum(?: value)?(?: is)?|less than or equal to|<=|up to|not exceed)\D{0,12}(\d{3,7})", _re.I),
    _re.compile(r"(?:max_tokens|max_completion_tokens)[^0-9]{0,60}?(\d{3,7})", _re.I),
)


def _parse_output_cap(text: str) -> int | None:
    """Pull the provider's output-token ceiling out of a 400 error body."""
    for rx in _CAP_RES:
        m = rx.search(text or "")
        if m:
            n = int(m.group(1))
            if 256 <= n <= 1_000_000:
                return n
    return None


_RETRY_STATUS = {429, 500, 502, 503, 529}
_MAX_RETRIES = int(os.getenv("CUSTOM_LLM_MAX_RETRIES", "2"))

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
        max_tokens = min(max_tokens, _MAX_OUT_CAP.get(route, max_tokens))
        payload["max_completion_tokens" if route in _USE_MAX_COMPLETION_TOKENS else "max_tokens"] = max_tokens
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        def _post(body: dict):
            """POST with a short back-off on rate limits / transient 5xx."""
            for attempt in range(_MAX_RETRIES + 1):
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={**headers, "Content-Type": "application/json; charset=utf-8"},
                    data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                    timeout=self.timeout,
                )
                if resp.status_code not in _RETRY_STATUS or attempt == _MAX_RETRIES:
                    return resp
                try:
                    wait = float(resp.headers.get("retry-after", ""))
                except ValueError:
                    wait = 2.0 * (attempt + 1)
                _time.sleep(min(max(wait, 1.0), 20.0))
            return resp  # pragma: no cover

        try:
            r = _post(payload)
            # Some models reject parameters other models require
            # ("`temperature` is deprecated for this model", "use max_completion_tokens",
            # "max_tokens must be <= 8192"). Fix the request, retry, and remember it.
            for _ in range(3):
                if r.status_code != 400:
                    break
                low = r.text.lower()
                retry = dict(payload)
                changed = False
                if "temperature" in low and "temperature" in retry:
                    retry.pop("temperature")
                    _NO_TEMPERATURE.add(route)
                    changed = True
                elif "max_completion_tokens" in low and "max_tokens" in retry:
                    retry["max_completion_tokens"] = retry.pop("max_tokens")
                    _USE_MAX_COMPLETION_TOKENS.add(route)
                    changed = True
                else:
                    key = "max_completion_tokens" if "max_completion_tokens" in retry else "max_tokens"
                    cap = _parse_output_cap(r.text) if ("max_tokens" in low or "max_completion_tokens" in low
                                                         or "output" in low) else None
                    if cap and cap < retry.get(key, 0):
                        retry[key] = cap
                        _MAX_OUT_CAP[route] = cap
                        changed = True
                if not changed:
                    break
                payload = retry
                r = _post(payload)
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
