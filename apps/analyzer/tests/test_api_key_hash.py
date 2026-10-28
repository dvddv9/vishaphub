# -*- coding: utf-8 -*-
"""API keys are stored as a hash, never in plaintext (v6.5).

v6.5-P0: the digest is HMAC-SHA256 keyed with ``API_KEY_PEPPER``, not a plain
sha256 — an unkeyed digest lets anyone with a table dump test candidate keys
offline. The pepper comes from the test fixture in ``conftest.py``.
"""
import hashlib
import hmac
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api import tenants


def _store():
    """TenantStore with a mocked async session."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)

    with patch("src.api.tenants.create_async_engine", return_value=MagicMock()), \
         patch("src.api.tenants.async_sessionmaker", return_value=factory):
        return tenants.TenantStore("postgresql+asyncpg://u:p@localhost/db"), session


def test_hash_api_key_matches_hmac():
    key = "vishap_live_example"
    pepper = os.environ["API_KEY_PEPPER"]

    assert tenants.hash_api_key(key) == hmac.new(
        pepper.encode("utf-8"), key.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert len(tenants.hash_api_key(key)) == 64
    assert tenants.hash_api_key(key) != tenants.hash_api_key(key + "x")


@pytest.mark.asyncio
async def test_create_stores_hash_only():
    store, session = _store()
    key = "vishap_live_secret_value"

    await store.create(tenant_id="tenant_1", api_key=key, plan="pro", email="a@b.c")

    model = session.add.call_args[0][0]
    assert model.api_key is None, "plaintext key must never be persisted"
    assert model.api_key_hash == tenants.hash_api_key(key)


@pytest.mark.asyncio
async def test_lookup_hashes_the_presented_key():
    store, _ = _store()

    with patch.object(
        store, "get_by_hash", AsyncMock(return_value={"tenant_id": "tenant_1"})
    ) as by_hash:
        result = await store.get_by_api_key("vishap_live_secret_value")

    by_hash.assert_awaited_once_with(
        tenants.hash_api_key("vishap_live_secret_value")
    )
    assert result == {"tenant_id": "tenant_1"}
