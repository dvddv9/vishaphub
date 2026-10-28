"""Model resolution: operator mode and bring-your-own-key must never blur."""
import pytest

from core.llm_config import ConfigError, resolve

SERVER_ENV = {
    "CUSTOM_LLM_KEY": "server-key",
    "CUSTOM_LLM_MODEL": "claude-sonnet-5-5",
    "CUSTOM_LLM_URL": "https://api.anthropic.com/v1",
}


def test_operator_mode_uses_the_server_key():
    config = resolve({}, SERVER_ENV)
    assert config.key == "server-key"
    assert config.from_client is False


def test_byok_wins_over_the_server_key():
    config = resolve({"x-llm-api-key": "client-key", "x-llm-model": "claude-haiku-5-5"}, SERVER_ENV)
    assert config.key == "client-key"
    assert config.from_client is True


def test_server_only_rejects_a_client_key():
    with pytest.raises(ConfigError, match="operator's key"):
        resolve({"x-llm-api-key": "client-key", "x-llm-model": "m"},
                {**SERVER_ENV, "VISHAP_SERVER_KEY_ONLY": "1"})


def test_server_only_without_a_client_key_still_works():
    config = resolve({}, {**SERVER_ENV, "VISHAP_SERVER_KEY_ONLY": "1"})
    assert config.key == "server-key"


def test_require_user_key_without_a_key_fails():
    with pytest.raises(ConfigError, match="requires your own key"):
        resolve({}, {**SERVER_ENV, "VISHAP_REQUIRE_USER_LLM_KEY": "1"})


def test_byok_requires_a_model():
    with pytest.raises(ConfigError, match="model is required"):
        resolve({"x-llm-api-key": "client-key"}, {})


def test_unknown_provider_is_rejected():
    with pytest.raises(ConfigError, match="unsupported provider"):
        resolve({"x-llm-provider": "not-a-provider"}, SERVER_ENV)


def test_custom_provider_requires_a_url():
    with pytest.raises(ConfigError, match="url is required"):
        resolve({"x-llm-api-key": "k", "x-llm-model": "m", "x-llm-provider": "custom"}, {})


def test_url_must_be_http():
    with pytest.raises(ConfigError, match="http"):
        resolve({"x-llm-api-key": "k", "x-llm-model": "m", "x-llm-provider": "custom", "x-llm-url": "file:///etc/passwd"}, {})


def test_nothing_configured_is_an_error_not_a_silent_default():
    with pytest.raises(ConfigError, match="no model configured"):
        resolve({}, {})


def test_public_view_hides_the_key():
    config = resolve({}, SERVER_ENV)
    public = config.as_public()
    assert "key" not in public or "server-key" not in str(public)
    assert public["has_key"] is True
