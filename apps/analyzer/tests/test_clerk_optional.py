# -*- coding: utf-8 -*-
"""Clerk as an optional dependency of the API (v6.4).

`/analyze/secure` must answer 401 with a clear message when Clerk is not
configured — not raise at import time and not return 500.
"""
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.auth import clerk
from src.auth.middleware import current_user


@pytest.fixture(autouse=True)
def _clear_clerk(monkeypatch):
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    clerk._jwks_cache.clear()


def test_clerk_disabled_no_key():
    from src.main import app

    # The header has to be present, otherwise current_user stops at
    # "Missing or invalid Authorization header" before reaching Clerk.
    response = TestClient(app).post(
        "/analyze/secure",
        json={"material": "print(1)", "filename": "a.py"},
        headers={"Authorization": "Bearer stub"},
    )

    assert response.status_code == 401
    assert "Clerk not configured" in response.json()["detail"]


def test_clerk_enabled_with_key(monkeypatch):
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_stub")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://clerk.test/jwks")
    assert clerk.is_configured() is True

    api = FastAPI()

    @api.get("/whoami")
    async def whoami(user=Depends(current_user)):
        return user

    with patch(
        "src.auth.middleware.verify_jwt",
        return_value={"sub": "user-1", "org_id": "org-9"},
    ):
        response = TestClient(api).get(
            "/whoami", headers={"Authorization": "Bearer stub"}
        )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == "org-9"
