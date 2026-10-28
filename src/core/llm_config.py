"""Which model answers this request — decided once, the same way in every service.

Two modes, and they must not blur:

* **operator mode** — the server's own key and model answer, callers cannot change them;
* **bring-your-own-key** — the caller sends provider, model and key per request, and the
  server never stores them.

The analyser and the generator each grew their own version of this; the difference
between them was accidental, not designed. Here the decision is a value, not a route.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

PROVIDERS = ("custom", "anthropic", "openai", "groq", "openrouter", "mistral", "deepseek", "ollama")

#: Providers that need an explicit URL — they have no single well-known endpoint.
NEEDS_URL = {"custom", "ollama"}


class ConfigError(ValueError):
    """The request asked for something the server will not do."""


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    url: str = ""
    model: str = ""
    key: str = ""
    from_client: bool = False

    def as_public(self) -> dict:
        """What may be echoed back: never the key itself."""
        return {
            "provider": self.provider,
            "url": self.url,
            "model": self.model,
            "from_client": self.from_client,
            "has_key": bool(self.key),
        }


def _clean(value: str | None) -> str:
    return (value or "").strip()


def resolve(headers: dict, env: dict) -> ModelConfig:
    """Pick the model for one request.

    Header names are lowercase; values that reason about the environment use ``env``
    so a call can be replayed with a different deployment without monkeypatching.
    """
    server_only = _clean(env.get("VISHAP_SERVER_KEY_ONLY")).lower() in {"1", "true", "yes", "on"}
    require_user = _clean(env.get("VISHAP_REQUIRE_USER_LLM_KEY")).lower() in {"1", "true", "yes", "on"}

    provider = _clean(headers.get("x-llm-provider") or env.get("LLM_PROVIDER") or "custom").lower()
    url = _clean(headers.get("x-llm-url") or env.get("CUSTOM_LLM_URL"))
    model = _clean(headers.get("x-llm-model") or env.get("CUSTOM_LLM_MODEL"))
    client_key = _clean(headers.get("x-llm-api-key"))

    if provider not in PROVIDERS:
        raise ConfigError(f"unsupported provider: {provider}")

    if server_only:
        if client_key:
            raise ConfigError("this deployment uses the operator's key; per-request keys are not accepted")
        return ModelConfig(provider, url, model, _clean(env.get("CUSTOM_LLM_KEY")), from_client=False)

    if client_key:
        if not model:
            raise ConfigError("model is required when you bring your own key")
        if provider in NEEDS_URL:
            if not url:
                raise ConfigError(f"url is required for provider {provider}")
            if urlparse(url).scheme not in ("http", "https"):
                raise ConfigError("url must start with http:// or https://")
        return ModelConfig(provider, url, model, client_key, from_client=True)

    if require_user:
        raise ConfigError("this deployment requires your own key")

    key = _clean(env.get("CUSTOM_LLM_KEY"))
    if not key:
        raise ConfigError("no model configured and no key supplied")
    return ModelConfig(provider, url, model, key, from_client=False)
