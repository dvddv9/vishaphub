# -*- coding: utf-8 -*-
"""v7.4.7: daily cap not bypassable by X-LLM-Api-Key in server-key-only mode,
current_tenant 401 on a bad token / key gate without one, Clerk JWKS TTL + iss/azp."""
import asyncio
import json
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from src.api import rate_limit
from src.auth import clerk
from src.auth import middleware as mw


def _req(headers=None, host="9.9.9.9"):
    return SimpleNamespace(headers=headers or {}, client=SimpleNamespace(host=host))


def _run(coro):
    return asyncio.run(coro)


# ---- daily cap -----------------------------------------------------------
@pytest.fixture
def daily(monkeypatch):
    monkeypatch.setattr(rate_limit, "LIMIT_DAILY", 2)
    monkeypatch.setenv("VISHAP_DAILY_LIMIT_GLOBAL", "0")
    monkeypatch.delenv("VISHAP_TRUSTED_PROXY_HOPS", raising=False)
    rate_limit._DAY_COUNTS.clear()
    yield
    rate_limit._DAY_COUNTS.clear()


def test_junk_llm_key_does_not_lift_cap_in_server_key_only_mode(monkeypatch, daily):
    monkeypatch.setenv("VISHAP_SERVER_KEY_ONLY", "1")
    r = _req({"x-llm-api-key": "junk"})
    _run(rate_limit.rate_limit_daily(r))
    _run(rate_limit.rate_limit_daily(r))
    with pytest.raises(HTTPException) as e:
        _run(rate_limit.rate_limit_daily(r))
    assert e.value.status_code == 429


def test_own_llm_key_still_skips_cap_when_caller_pays(monkeypatch, daily):
    monkeypatch.delenv("VISHAP_SERVER_KEY_ONLY", raising=False)
    r = _req({"x-llm-api-key": "sk-real"})
    for _ in range(5):
        _run(rate_limit.rate_limit_daily(r))


def test_keyless_caller_is_capped(monkeypatch, daily):
    monkeypatch.delenv("VISHAP_SERVER_KEY_ONLY", raising=False)
    r = _req()
    _run(rate_limit.rate_limit_daily(r))
    _run(rate_limit.rate_limit_daily(r))
    with pytest.raises(HTTPException):
        _run(rate_limit.rate_limit_daily(r))


# ---- current_tenant ------------------------------------------------------
def test_bad_or_expired_bearer_is_401_not_default_tenant(monkeypatch):
    def boom(_token):
        raise mw.AuthError("Token expired")
    monkeypatch.setattr(mw, "verify_jwt", boom)
    with pytest.raises(HTTPException) as e:
        _run(mw.current_tenant(authorization="Bearer stale", x_api_key=None))
    assert e.value.status_code == 401


def test_valid_bearer_gives_org_then_user(monkeypatch):
    monkeypatch.setattr(mw, "verify_jwt", lambda _t: {"sub": "u1", "org_id": "org1"})
    assert _run(mw.current_tenant(authorization="Bearer x", x_api_key=None)) == "org1"
    monkeypatch.setattr(mw, "verify_jwt", lambda _t: {"sub": "u1"})
    assert _run(mw.current_tenant(authorization="Bearer x", x_api_key=None)) == "u1"


def test_no_bearer_needs_the_api_key_gate(monkeypatch):
    import src.api.auth as auth

    async def deny(_key):
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    monkeypatch.setattr(auth, "verify_api_key", deny)
    with pytest.raises(HTTPException) as e:
        _run(mw.current_tenant(authorization=None, x_api_key=None))
    assert e.value.status_code == 401

    async def allow(_key):
        return None
    monkeypatch.setattr(auth, "verify_api_key", allow)
    assert _run(mw.current_tenant(authorization=None, x_api_key="k")) == mw._FALLBACK_TENANT


# ---- Clerk ---------------------------------------------------------------
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks(kid):
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key()))
    jwk["kid"] = kid
    return {"keys": [jwk]}


def _token(kid="k1", **extra):
    claims = {"sub": "u1", "exp": int(time.time()) + 60, **extra}
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def clerk_env(monkeypatch):
    monkeypatch.setenv("CLERK_JWKS_URL", "https://clerk.test/jwks")
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    monkeypatch.delenv("CLERK_AUTHORIZED_PARTIES", raising=False)
    clerk._jwks_cache.clear()
    yield
    clerk._jwks_cache.clear()


def _serve(monkeypatch, docs):
    """httpx.get stub returning docs[i] on the i-th call (last one repeats)."""
    calls = []

    def get(url, timeout=10):
        doc = docs[min(len(calls), len(docs) - 1)]
        calls.append(url)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: doc)
    monkeypatch.setattr(clerk.httpx, "get", get)
    return calls


def test_jwks_is_cached_within_ttl(monkeypatch, clerk_env):
    calls = _serve(monkeypatch, [_jwks("k1")])
    clerk.verify_jwt(_token())
    clerk.verify_jwt(_token())
    assert len(calls) == 1


def test_jwks_refetched_after_ttl(monkeypatch, clerk_env):
    calls = _serve(monkeypatch, [_jwks("k1")])
    clerk.verify_jwt(_token())
    url, (_t, doc) = next(iter(clerk._jwks_cache.items()))
    clerk._jwks_cache[url] = (_t - clerk._JWKS_TTL - 1, doc)
    clerk.verify_jwt(_token())
    assert len(calls) == 2


def test_rotated_key_is_picked_up_without_restart(monkeypatch, clerk_env):
    calls = _serve(monkeypatch, [_jwks("old"), _jwks("new")])
    clerk.verify_jwt(_token("old"))
    url, (_t, doc) = next(iter(clerk._jwks_cache.items()))
    clerk._jwks_cache[url] = (_t - clerk._JWKS_MIN_REFRESH - 1, doc)   # not just refreshed
    assert clerk.verify_jwt(_token("new"))["sub"] == "u1"
    assert len(calls) == 2


def test_unknown_kid_cannot_force_a_refetch_every_request(monkeypatch, clerk_env):
    calls = _serve(monkeypatch, [_jwks("k1")])
    clerk.verify_jwt(_token("k1"))
    for _ in range(5):
        with pytest.raises(clerk.AuthError):
            clerk.verify_jwt(_token("nope"))
    assert len(calls) == 1


def test_issuer_enforced_only_when_configured(monkeypatch, clerk_env):
    _serve(monkeypatch, [_jwks("k1")])
    clerk.verify_jwt(_token(iss="https://other.example"))          # not enforced
    monkeypatch.setenv("CLERK_ISSUER", "https://mine.clerk.accounts.dev")
    with pytest.raises(clerk.AuthError):
        clerk.verify_jwt(_token(iss="https://other.example"))
    with pytest.raises(clerk.AuthError):
        clerk.verify_jwt(_token())                                  # no iss at all
    assert clerk.verify_jwt(_token(iss="https://mine.clerk.accounts.dev"))["sub"] == "u1"


def test_azp_enforced_only_when_configured(monkeypatch, clerk_env):
    _serve(monkeypatch, [_jwks("k1")])
    clerk.verify_jwt(_token(azp="https://evil.example"))            # not enforced
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://app.example, https://vishap.example")
    with pytest.raises(clerk.AuthError):
        clerk.verify_jwt(_token(azp="https://evil.example"))
    assert clerk.verify_jwt(_token(azp="https://vishap.example"))["sub"] == "u1"
