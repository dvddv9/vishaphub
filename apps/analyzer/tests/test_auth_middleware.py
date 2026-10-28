# -*- coding: utf-8 -*-
"""Tests for the Clerk auth FastAPI dependency (v6.1)."""
import json
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.auth import clerk
from src.auth.middleware import current_user

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUB = _KEY.public_key()


def _jwks():
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_PUB))
    jwk["kid"] = "test-kid"
    return {"keys": [jwk]}


def _token(claims):
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": "test-kid"})


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("CLERK_JWKS_URL", "https://clerk.test/jwks")
    clerk._jwks_cache.clear()


@pytest.fixture
def client():
    api = FastAPI()

    @api.get("/whoami")
    async def whoami(user=Depends(current_user)):
        return user

    return TestClient(api)


def test_current_user_from_jwt(client):
    token = _token({"sub": "user-1", "exp": int(time.time()) + 600})
    with patch("src.auth.clerk.httpx.get") as get:
        get.return_value = MagicMock(status_code=200)
        get.return_value.json.return_value = _jwks()
        r = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["user_id"] == "user-1"


def test_current_user_missing_token(client):
    r = client.get("/whoami")
    assert r.status_code == 401


def test_current_user_invalid_token(client):
    with patch("src.auth.clerk.httpx.get") as get:
        get.return_value = MagicMock(status_code=200)
        get.return_value.json.return_value = _jwks()
        r = client.get("/whoami", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401
