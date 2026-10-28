# -*- coding: utf-8 -*-
"""Clerk JWT verification tests (v6.5) — real RS256 crypto, mocked JWKS fetch.

No network: `_fetch_jwks` is patched, everything else is the production path.
"""
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.auth import clerk

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()


def _jwks(kid: str = "test-kid") -> dict:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_PUBLIC_KEY))
    jwk["kid"] = kid
    return {"keys": [jwk]}


def _token(claims: dict, key=None, kid: str = "test-kid") -> str:
    return jwt.encode(claims, key or _PRIVATE_KEY, algorithm="RS256", headers={"kid": kid})


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("CLERK_JWKS_URL", "https://clerk.test/jwks")
    clerk._jwks_cache.clear()


def test_verify_jwt_accepts_valid_token(monkeypatch):
    monkeypatch.setattr(clerk, "_fetch_jwks", lambda: _jwks())
    token = _token({"sub": "user-1", "org_id": "org-9", "exp": int(time.time()) + 60})

    claims = clerk.verify_jwt(token)

    assert claims["sub"] == "user-1"
    assert claims["org_id"] == "org-9"


def test_verify_jwt_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr(clerk, "_fetch_jwks", lambda: _jwks())
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _token({"sub": "user-1", "exp": int(time.time()) + 60}, key=other_key)

    with pytest.raises(clerk.AuthError):
        clerk.verify_jwt(token)
