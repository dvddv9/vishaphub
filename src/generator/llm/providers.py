"""LLM client for any OpenAI-compatible chat endpoint. Standard library only.

Configuration comes from the environment, the same names as in Vishap:

  VISHAP_LLM_PROVIDER  must be "custom" (the default)
  CUSTOM_LLM_URL       base URL, e.g. https://api.example.com/v1  (required)
  CUSTOM_LLM_MODEL     model name                                  (required)
  CUSTOM_LLM_KEY       API key; required unless the URL is localhost
  CUSTOM_LLM_THINKING  optional: enabled | disabled. Sent as
                       {"thinking": {"type": ...}} (DeepSeek). Unset: not sent.
  CUSTOM_LLM_REASONING_EFFORT  optional: low | high | max. Sent as
                       reasoning_effort. Unset: not sent.

The two optional fields are not part of every OpenAI-compatible API, so
they are sent only when set.

There is no default URL: a forgotten variable must not send a spec to a
provider nobody chose. Plain http is allowed only for localhost (Ollama
and similar), so a key never crosses the network unencrypted. The key is
never put into an error message or a repr.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass, field

DEFAULT_TIMEOUT = 60.0
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MAX_KEY_LENGTH = 200
KEY_RE = re.compile(r"^[\x21-\x7E]+$")  # printable ASCII, no spaces
THINKING_VALUES = frozenset({"enabled", "disabled"})
EFFORT_VALUES = frozenset({"low", "high", "max"})


class LLMConfigError(ValueError):
    """The environment does not describe a usable endpoint."""


@dataclass(frozen=True)
class LLMConfig:
    url: str
    model: str
    key: str = field(default="", repr=False)
    timeout: float = DEFAULT_TIMEOUT
    thinking: str = ""
    reasoning_effort: str = ""

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
    key = env.get("CUSTOM_LLM_KEY", "").strip()
    if key and (len(key) > MAX_KEY_LENGTH or not KEY_RE.match(key)):
        raise LLMConfigError(
            f"CUSTOM_LLM_KEY does not look like an API key (length {len(key)}; "
            "it must be printable ASCII without spaces, at most "
            f"{MAX_KEY_LENGTH} characters). Was something else in the clipboard?")
    if not key and urllib.parse.urlsplit(url).hostname not in LOCAL_HOSTS:
        raise LLMConfigError("CUSTOM_LLM_KEY is not set (only a localhost server may go without one)")
    thinking = env.get("CUSTOM_LLM_THINKING", "").strip().lower()
    if thinking and thinking not in THINKING_VALUES:
        raise LLMConfigError("CUSTOM_LLM_THINKING must be enabled or disabled")
    effort = env.get("CUSTOM_LLM_REASONING_EFFORT", "").strip().lower()
    if effort and effort not in EFFORT_VALUES:
        raise LLMConfigError("CUSTOM_LLM_REASONING_EFFORT must be low, high or max")
    return LLMConfig(url=url, model=model, key=key,
                     thinking=thinking, reasoning_effort=effort)
