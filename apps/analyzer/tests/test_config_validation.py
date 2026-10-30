# -*- coding: utf-8 -*-
"""Startup configuration validation tests (v6.4)."""
import pytest

from src import config


def _clear_required(monkeypatch) -> None:
    for name in config.REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("VISHAP_DEV", raising=False)


def test_validate_config_raises_when_missing(monkeypatch):
    _clear_required(monkeypatch)

    with pytest.raises(RuntimeError) as excinfo:
        config.validate_config()

    message = str(excinfo.value)
    assert "Missing env vars" in message
    assert ".env.example" in message
    for name in config.REQUIRED_ENV_VARS:
        assert name in message


def test_validate_config_dev_mode_warns(monkeypatch):
    _clear_required(monkeypatch)
    monkeypatch.setenv("VISHAP_DEV", "true")

    with pytest.warns(RuntimeWarning):
        missing = config.validate_config()

    assert set(missing) == set(config.REQUIRED_ENV_VARS)


def test_validate_config_passes_when_all_set(monkeypatch):
    for name in config.REQUIRED_ENV_VARS:
        monkeypatch.setenv(name, "configured")
    monkeypatch.delenv("VISHAP_DEV", raising=False)

    assert config.validate_config() == []


# === v6.6: a placeholder pepper is not a secret ===

def test_validate_secrets_rejects_placeholder_pepper(monkeypatch):
    monkeypatch.setenv("API_KEY_PEPPER", "change-me-in-production")
    monkeypatch.setenv("VISHAP_TENANT_KEYS", "true")

    with pytest.raises(RuntimeError) as excinfo:
        config.validate_secrets(strict=True)

    assert "placeholder" in str(excinfo.value)


def test_validate_secrets_rejects_missing_pepper_when_tenants_on(monkeypatch):
    monkeypatch.delenv("API_KEY_PEPPER", raising=False)
    monkeypatch.setenv("VISHAP_TENANT_KEYS", "true")

    with pytest.raises(RuntimeError) as excinfo:
        config.validate_secrets(strict=True)

    assert "not set" in str(excinfo.value)


def test_validate_secrets_accepts_real_pepper(monkeypatch):
    monkeypatch.setenv("API_KEY_PEPPER", "k9Xq2Lm7vT4bR1sN8yH3wZ6aD0fG5jC")
    monkeypatch.setenv("VISHAP_TENANT_KEYS", "true")

    assert config.validate_secrets() == []


def test_validate_secrets_warns_but_starts_when_tenants_off(monkeypatch):
    monkeypatch.setenv("API_KEY_PEPPER", "change-me-in-production")
    monkeypatch.setenv("VISHAP_TENANT_KEYS", "false")
    monkeypatch.setenv("VISHAP_DEV", "true")

    with pytest.warns(RuntimeWarning):
        problems = config.validate_secrets()

    assert problems
