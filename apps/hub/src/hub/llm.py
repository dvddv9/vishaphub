"""Which model the hub talks to, and how.

Three providers, chosen by the operator in the environment - never by a request body, so a client cannot
point the hub at an address of its own choosing:

* ``anthropic`` (the default) - the Messages API, ``https://api.anthropic.com`` unless ``VISHAP_HUB_LLM_URL``
  names another address (a company gateway, a proxy);
* ``openai`` - any server that speaks the OpenAI chat-completions dialect: OpenAI itself, Ollama, vLLM,
  LM Studio, llama.cpp, OpenRouter, a corporate gateway. ``VISHAP_HUB_LLM_URL`` is its base URL (``.../v1``)
  and ``VISHAP_HUB_LLM_MODEL`` names the model, because there is no sensible default;
* ``deepseek`` - DeepSeek's OpenAI-compatible API at its fixed address, default model ``deepseek-flash``
  (override with ``VISHAP_HUB_LLM_MODEL``);
* ``none`` - no model. The rules and the validator still run; nothing is sent anywhere.

This module builds a request and reads an answer. It does not open a connection: ``proposal.py`` and
``chat.py`` do that (and redact what they send), so there is still one place per feature where text leaves
the process, and the existing redaction and metering stay where they were.

Settings (all environment variables):

``VISHAP_HUB_LLM_PROVIDER``      anthropic | openai | deepseek | none
``VISHAP_HUB_LLM_URL``           base URL of the provider
``VISHAP_HUB_LLM_MODEL``         model name
``VISHAP_HUB_LLM_KEY``           the key, when the provider wants one
``VISHAP_HUB_LLM_KEY_REQUIRED``  1 / 0 to force; by default a key is needed unless the URL is this machine
``VISHAP_HUB_LLM_TIMEOUT``       seconds to wait for an answer (a local model may need more than the default)
"""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from urllib.parse import urlparse

from . import egress

PROVIDERS = ("anthropic", "openai", "deepseek", "ollama", "none")
ANTHROPIC_BASE = "https://api.anthropic.com"
OPENAI_BASE = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"
DEEPSEEK_BASE = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-flash"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
OLLAMA_BASE = "http://localhost:11434/v1"
DEFAULT_OLLAMA_MODEL = "llama3.1"

#: what a visitor may pick on the page. A NAME, never an address: the address is fixed here.
PRESETS = {
    "anthropic": ("anthropic", ANTHROPIC_BASE, DEFAULT_ANTHROPIC_MODEL),
    "deepseek": ("openai", DEEPSEEK_BASE, DEFAULT_DEEPSEEK_MODEL),
    "openai": ("openai", OPENAI_BASE, DEFAULT_OPENAI_MODEL),
    "ollama": ("openai", OLLAMA_BASE, DEFAULT_OLLAMA_MODEL),
}
_BUILT_IN = ("anthropic", "deepseek", "openai", "ollama")


def _loopback_only() -> bool:
    """The hub listens on this machine only. Then «the Ollama on this machine» is the visitor's own."""
    return _env("VISHAP_HUB_HOST").lower() in ("127.0.0.1", "localhost", "::1")

#: a name that means "this machine" from inside a container as well
_LOCAL_NAMES = {"localhost", "host.docker.internal"}


class ConfigError(ValueError):
    """The operator's settings cannot be used. The message says what to change."""


@dataclass(frozen=True)
class Settings:
    provider: str
    base_url: str
    model: str
    key_required: bool


@dataclass(frozen=True)
class Reply:
    text: str
    truncated: bool
    usage: object


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def is_local(url: str) -> bool:
    """True when the URL names this machine: loopback or ``host.docker.internal``."""
    host = (urlparse(url).hostname or "").lower()
    if host in _LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def settings(model: str = "", preset: str = "") -> Settings:
    """The operator's choice, validated. Raises ConfigError with the thing to fix.

    ``preset`` is the name a visitor picked on the page (``anthropic`` or ``deepseek``). It is honoured only
    when the operator left the model open (provider anthropic with no custom address, or DeepSeek), so a
    visitor can swap one fixed provider for another but can never point the hub anywhere new.
    """
    provider = (_env("VISHAP_HUB_LLM_PROVIDER") or "anthropic").lower()
    if provider not in PROVIDERS:
        raise ConfigError(f"VISHAP_HUB_LLM_PROVIDER={provider!r} is not one of: {', '.join(PROVIDERS)}")
    if provider == "none":
        return Settings("none", "", "", False)

    operator = provider
    custom_url = _env("VISHAP_HUB_LLM_URL").rstrip("/")
    preset = (preset or "").strip().lower()
    # A visitor's pick swaps one built-in provider for another. It never applies to a custom address.
    picked = (preset in PRESETS and preset != operator and operator in _BUILT_IN and not custom_url
              and (preset != "ollama" or _loopback_only()))
    if picked:
        provider, env_model, base = preset, "", ""
    else:
        env_model, base = _env("VISHAP_HUB_LLM_MODEL"), custom_url
    base = base or {"anthropic": ANTHROPIC_BASE, "deepseek": DEEPSEEK_BASE, "ollama": OLLAMA_BASE}.get(provider, OPENAI_BASE)
    wire = "anthropic" if provider == "anthropic" else "openai"
    parsed = urlparse(base)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ConfigError(f"VISHAP_HUB_LLM_URL={base!r} is not an http(s) address")
    if egress.offline() and not egress.url_allowed(base):
        raise ConfigError(f"offline mode: the model address {parsed.hostname} is not on the private network; "
                          "point VISHAP_HUB_LLM_URL at a local server or list the host in VISHAP_HUB_ALLOWED_HOSTS")

    name = (model or env_model).strip()
    if not name:
        if provider == "anthropic":
            name = DEFAULT_ANTHROPIC_MODEL
        elif provider == "deepseek":
            name = DEFAULT_DEEPSEEK_MODEL
        elif picked and provider in PRESETS:
            name = PRESETS[provider][2]
        elif provider == "ollama":
            name = DEFAULT_OLLAMA_MODEL
        else:
            raise ConfigError("set VISHAP_HUB_LLM_MODEL: the openai provider has no default model")

    flag = _env("VISHAP_HUB_LLM_KEY_REQUIRED").lower()
    if flag in ("0", "false", "no", "off"):
        required = False
    elif flag in ("1", "true", "yes", "on"):
        required = True
    else:
        required = not is_local(base)
    return Settings(wire, base, name, required)


def key_for(api_key: str = "", preset: str = "") -> str:
    """The key to send: the caller's own, else the operator's - but the operator's key is never sent to a
    provider the operator did not choose."""
    own = (api_key or "").strip()
    if own:
        return own
    operator = (_env("VISHAP_HUB_LLM_PROVIDER") or "anthropic").lower()
    preset = (preset or "").strip().lower()
    if preset in PRESETS and preset != operator:
        return ""
    if operator == "ollama":
        return _env("VISHAP_HUB_LLM_KEY")
    return _env("VISHAP_HUB_LLM_KEY")


def available(api_key: str = "", preset: str = "") -> bool:
    """Would a model call be attempted for this caller? False for provider none, for a settings error and for
    a missing key where one is required. Used where the answer decides whether a request costs anything."""
    try:
        current = settings(preset=preset)
    except ConfigError:
        return False
    if current.provider == "none":
        return False
    return bool(key_for(api_key, preset)) or not current.key_required


def timeout(default: int) -> int:
    raw = _env("VISHAP_HUB_LLM_TIMEOUT")
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def endpoint(current: Settings) -> str:
    if current.provider == "anthropic":
        return current.base_url + ("/messages" if current.base_url.endswith("/v1") else "/v1/messages")
    return current.base_url + "/chat/completions"


def request_parts(current: Settings, key: str, system: str, messages: list[dict],
                  max_tokens: int) -> tuple[str, dict, dict]:
    """(url, headers, payload) for one call. The caller sends it; nothing is opened here."""
    key = (key or "").strip()
    if current.provider == "anthropic":
        headers = {"anthropic-version": "2023-06-01", "content-type": "application/json"}
        if key:
            headers["x-api-key"] = key
        payload = {"model": current.model, "max_tokens": max_tokens, "system": system, "messages": messages}
    else:
        headers = {"content-type": "application/json"}
        if key:
            headers["authorization"] = f"Bearer {key}"
        # OpenAI's own newer models refuse max_tokens; local servers and most gateways only know it.
        field = "max_completion_tokens" if urlparse(current.base_url).hostname == "api.openai.com" else "max_tokens"
        payload = {"model": current.model, field: max_tokens,
                   "messages": [{"role": "system", "content": system}, *messages]}
    return endpoint(current), headers, payload


def read_reply(current: Settings, data: object) -> Reply:
    """The text, whether the limit cut it, and the provider's usage block, from either dialect."""
    if not isinstance(data, dict):
        return Reply("", False, None)
    if current.provider == "anthropic":
        parts = [b.get("text", "") for b in (data.get("content") or [])
                 if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(part for part in parts if part).strip()
        return Reply(text, data.get("stop_reason") == "max_tokens", data.get("usage"))

    choices = data.get("choices")
    first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = message.get("content")
    if isinstance(content, list):
        content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    text = content.strip() if isinstance(content, str) else ""
    return Reply(text, first.get("finish_reason") == "length", data.get("usage"))
