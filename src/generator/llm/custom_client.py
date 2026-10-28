"""The custom provider: any OpenAI-compatible chat endpoint. Standard library only.

The analog of Vishap's `llm/custom_client.py`: the settings of the endpoint and the one HTTP call.

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

import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from generator.llm._scrub import short as _short

DEFAULT_TIMEOUT = 60.0
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MAX_KEY_LENGTH = 200
KEY_RE = re.compile(r"^[\x21-\x7E]+$")  # printable ASCII, no spaces
THINKING_VALUES = frozenset({"enabled", "disabled"})
EFFORT_VALUES = frozenset({"low", "high", "max"})


MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class LLMConfigError(ValueError):
    """The environment does not describe a usable endpoint."""


class CustomError(RuntimeError):
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
    thinking: str = ""
    reasoning_effort: str = ""
    temperature: float | None = None     # --repro sets 0 and a seed; None leaves it to the provider
    seed: int | None = None

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


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0


class CustomClient:
    """One chat request to the configured endpoint."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or config_from_env()

    def complete(self, messages: list[dict], max_tokens: int = 4096) -> Completion:
        cfg = self.config
        payload: dict = {"model": cfg.model, "messages": messages, "max_tokens": max_tokens}
        if cfg.thinking:
            payload["thinking"] = {"type": cfg.thinking}
        if cfg.reasoning_effort:
            payload["reasoning_effort"] = cfg.reasoning_effort
        if cfg.temperature is not None:
            payload["temperature"] = cfg.temperature
        if cfg.seed is not None:
            payload["seed"] = cfg.seed
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if cfg.key:
            headers["Authorization"] = f"Bearer {cfg.key}"
        req = urllib.request.Request(cfg.endpoint, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
                raw = resp.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as e:
            detail = _short(e.read() or b"", cfg.key)
            raise CustomError(f"endpoint answered {e.code}: {detail}", status=e.code) from None
        except (socket.timeout, TimeoutError):
            raise CustomError(f"no answer within {cfg.timeout:g}s") from None
        except urllib.error.URLError as e:
            reason = e.reason
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise CustomError(f"no answer within {cfg.timeout:g}s") from None
            raise CustomError(f"endpoint not reachable: {reason}") from None

        if len(raw) > MAX_RESPONSE_BYTES:
            raise CustomError("answer larger than 5 MB")
        try:
            data = json.loads(raw)
            choice = data["choices"][0]
            message = choice["message"]
            content = message.get("content")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise CustomError(f"answer is not a chat completion: {_short(raw, cfg.key)}") from None
        if not isinstance(content, str) or not content.strip():
            raise CustomError("answer has no text (" + _why_empty(data, choice, message) + ")")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return Completion(content, str(data.get("model") or cfg.model),
                          int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0))


def _why_empty(data: dict, choice: dict, message: dict) -> str:
    """Facts that explain an empty answer, without any of its content."""
    facts = [f"finish_reason={choice.get('finish_reason')}"]
    usage = data.get("usage") or {}
    if isinstance(usage, dict):
        for k in ("prompt_tokens", "completion_tokens"):
            if k in usage:
                facts.append(f"{k}={usage[k]}")
        details = usage.get("completion_tokens_details") or {}
        if isinstance(details, dict) and "reasoning_tokens" in details:
            facts.append(f"reasoning_tokens={details['reasoning_tokens']}")
    reasoning = message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        facts.append(f"reasoning_content of {len(reasoning)} chars")
    if choice.get("finish_reason") == "length":
        facts.append("the token limit ran out before the answer")
    return ", ".join(facts)
