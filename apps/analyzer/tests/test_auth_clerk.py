# -*- coding: utf-8 -*-
"""Tests for Clerk JWT verification (v6.1)."""
import json
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.auth import clerk

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUB = _KEY.public_key()


def _jwks():
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_PUB))
    jwk["kid"] = "test-kid"
    return {"keys": [jwk]}


def _token(claims, key=_KEY):
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-kid"})


def _mock_jwks(get):
    get.return_value = MagicMock(status_code=200)
    get.return_value.json.return_value = _jwks()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("CLERK_JWKS_URL", "https://clerk.test/jwks")
    clerk._jwks_cache.clear()


def test_verify_jwt_valid():
    token = _token({"sub": "user-1", "exp": int(time.time()) + 600})
    with patch("src.auth.clerk.httpx.get") as get:
        _mock_jwks(get)
        claims = clerk.verify_jwt(token)
    assert claims["sub"] == "user-1"


def test_verify_jwt_expired():
    token = _token({"sub": "u", "exp": int(time.time()) - 10})
    with patch("src.auth.clerk.httpx.get") as get:
        _mock_jwks(get)
        with pytest.raises(clerk.AuthError):
            clerk.verify_jwt(token)


def test_verify_jwt_invalid_signature():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _token({"sub": "u", "exp": int(time.time()) + 600}, key=other)
    with patch("src.auth.clerk.httpx.get") as get:
        _mock_jwks(get)
        with pytest.raises(clerk.AuthError):
            clerk.verify_jwt(token)


def test_verify_jwt_missing_claims():
    token = _token({"exp": int(time.time()) + 600})
    with patch("src.auth.clerk.httpx.get") as get:
        _mock_jwks(get)
        with pytest.raises(clerk.AuthError):
            clerk.verify_jwt(token)
