# -*- coding: utf-8 -*-
"""Tenant API-key verification tests (v6.5) — store mocked, no Postgres."""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.auth.middleware import verify_tenant_api_key

KEY = "vishap_live_test"


def _tenant(status: str = "active", expires_in_days: float | None = 30) -> dict:
    expires_at = (
        (datetime.now(UTC) + timedelta(days=expires_in_days)).isoformat()
        if expires_in_days is not None
        else None
    )
    return {
        "tenant_id": "tenant_abc",
        "api_key": KEY,
        "plan": "pro",
        "status": status,
        "email": "client@example.com",
        "expires_at": expires_at,
    }


@pytest.mark.asyncio
async def test_valid_key_returns_tenant():
    tenant = _tenant()
    with patch(
        "src.auth.middleware.get_tenant_by_api_key", AsyncMock(return_value=tenant)
    ) as lookup:
        result = await verify_tenant_api_key(KEY)

    lookup.assert_awaited_once_with(KEY)
    assert result == tenant


@pytest.mark.asyncio
async def test_expired_key_is_rejected():
    tenant = _tenant(expires_in_days=-1)
    with patch("src.auth.middleware.get_tenant_by_api_key", AsyncMock(return_value=tenant)):
        with pytest.raises(HTTPException) as excinfo:
            await verify_tenant_api_key(KEY)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "API key expired"


@pytest.mark.asyncio
async def test_missing_invalid_and_inactive_keys_are_rejected():
    with pytest.raises(HTTPException) as missing:
        await verify_tenant_api_key(None)
    assert missing.value.status_code == 401
    assert missing.value.detail == "Missing X-API-Key"

    with patch("src.auth.middleware.get_tenant_by_api_key", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as invalid:
            await verify_tenant_api_key("vishap_live_unknown")
    assert invalid.value.status_code == 401
    assert invalid.value.detail == "Invalid API key"

    with patch(
        "src.auth.middleware.get_tenant_by_api_key",
        AsyncMock(return_value=_tenant(status="canceled")),
    ):
        with pytest.raises(HTTPException) as inactive:
            await verify_tenant_api_key(KEY)
    assert inactive.value.status_code == 401
    assert "canceled" in inactive.value.detail
