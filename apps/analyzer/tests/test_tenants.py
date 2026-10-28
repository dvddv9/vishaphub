# -*- coding: utf-8 -*-
"""API key hashing: HMAC-SHA256 with a pepper (v6.5, P0).

The pepper lives in the environment, not in the database, so a table dump alone
is not enough to test candidate keys offline.
"""
import hashlib
import hmac

import pytest

from src.api.tenants import TenantStoreError, hash_api_key, legacy_hash_api_key

KEY = "vishap_live_example"


def test_hash_api_key_uses_pepper(monkeypatch):
    monkeypatch.setenv("API_KEY_PEPPER", "test-pepper")

    expected = hmac.new(b"test-pepper", KEY.encode("utf-8"), hashlib.sha256).hexdigest()
    assert hash_api_key(KEY) == expected
    # ...and it is not the unkeyed digest that was stored before v6.5.
    assert hash_api_key(KEY) != legacy_hash_api_key(KEY)

    # A missing pepper is a configuration error: fail loudly, never downgrade.
    monkeypatch.delenv("API_KEY_PEPPER", raising=False)
    with pytest.raises(TenantStoreError, match="API_KEY_PEPPER"):
        hash_api_key(KEY)


def test_hash_api_key_deterministic(monkeypatch):
    monkeypatch.setenv("API_KEY_PEPPER", "stable-pepper")

    assert hash_api_key(KEY) == hash_api_key(KEY)
    assert len(hash_api_key(KEY)) == 64
    assert hash_api_key(KEY) != hash_api_key(KEY + "x")


def test_hash_api_key_different_peppers(monkeypatch):
    monkeypatch.setenv("API_KEY_PEPPER", "pepper-one")
    first = hash_api_key(KEY)

    monkeypatch.setenv("API_KEY_PEPPER", "pepper-two")
    second = hash_api_key(KEY)

    assert first != second
