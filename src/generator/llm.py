"""LLM client for any OpenAI-compatible chat endpoint. Standard library only.

Configuration comes from the environment, the same names as in Vishap:

  VISHAP_LLM_PROVIDER  must be "custom" (the default)
  CUSTOM_LLM_URL       base URL, e.g. https://api.example.com/v1  (required)
  CUSTOM_LLM_MODEL     model name                                  (required)
  CUSTOM_LLM_KEY       API key; may be empty for a local server

There is no default URL: a forgotten variable must not send a spec to a
provider nobody chose. Plain http is allowed only for localhost (Ollama
and similar), so a key never crosses the network unencrypted. The key is
never put into an error message or a repr.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

DEFAULT_TIMEOUT = 60.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class LLMConfigError(ValueError):
    """The environment does not describe a usable endpoint."""


class LLMError(RuntimeError):
    """The endpoint was reached but did not give a usable answer."""

    def __init__(self, message: str, status: int | None = None):
        self.status = status
        super().__init__(message)


@dataclass(frozen=True)
class LLMConfig:
    url: str
    model: str
    key: str = field(default="", repr=False)
    timeout: float = DEFAULT_TIMEOUT

    @property
    def endpoint(self) -> str:
        return self.url.rstrip("/") + "/chat/completions"


def _check_url(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise LLMConfigError("CUSTOM_LLM_URL must be an http(s) URL with a host")
    if parts.scheme == "http" and parts.hostname not in LOCAL_HOSTS:
        raise LLMConfigError("CUSTOM_LLM_URL must use https unless it points at localhost")
    if parts.username or parts.password:
        raise LLMConfigError("CUSTOM_LLM_URL must not carry a user or password")


def config_from_env(env: dict | None = None) -> LLMConfig:
    env = os.environ if env is None else env
    provider = env.get("VISHAP_LLM_PROVIDER", "custom")
    if provider != "custom":
        raise LLMConfigError(f"VISHAP_LLM_PROVIDER={provider!r} is not supported; use custom")
    url = env.get("CUSTOM_LLM_URL", "").strip()
    if not url:
        raise LLMConfigError("CUSTOM_LLM_URL is not set")
    _check_url(url)
    model = env.get("CUSTOM_LLM_MODEL", "").strip()
    if not model:
        raise LLMConfigError("CUSTOM_LLM_MODEL is not set")
    return LLMConfig(url=url, model=model, key=env.get("CUSTOM_LLM_KEY", "").strip())


def _short(body: bytes, key: str) -> str:
    text = body[:500].decode("utf-8", errors="replace")
    return text.replace(key, "[key]") if key else text


def chat(messages: list[dict], config: LLMConfig | None = None,
         max_tokens: int = 4096) -> str:
    """Send one chat request and return the text of the first choice."""
    cfg = config or config_from_env()
    body = json.dumps({
        "model": cfg.model,
        "messages": messages,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg.key:
        headers["Authorization"] = f"Bearer {cfg.key}"
    req = urllib.request.Request(cfg.endpoint, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        detail = _short(e.read() or b"", cfg.key)
        raise LLMError(f"endpoint answered {e.code}: {detail}", status=e.code) from None
    except (socket.timeout, TimeoutError):
        raise LLMError(f"no answer within {cfg.timeout:g}s") from None
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise LLMError(f"no answer within {cfg.timeout:g}s") from None
        raise LLMError(f"endpoint not reachable: {reason}") from None

    if len(raw) > MAX_RESPONSE_BYTES:
        raise LLMError("answer larger than 5 MB")
    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError(f"answer is not a chat completion: {_short(raw, cfg.key)}") from None
    if not isinstance(content, str) or not content.strip():
        raise LLMError("answer has no text")
    return content
