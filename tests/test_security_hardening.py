# -*- coding: utf-8 -*-
"""Regression tests: SAML fail-closed, CORS allow-list, rate-limiter client IP."""
import importlib

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.api import rate_limit
from src.auth.saml_guard import validate_saml_assertion


def _request(xff=None, host="10.0.0.1"):
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": (host, 1234)})


# --- SAML --------------------------------------------------------------------
@pytest.mark.parametrize("payload", [{}, {"SAMLResponse": "x"}, {"SAMLResponse": "<forged/>"}, None])
def test_saml_guard_is_fail_closed(payload):
    assert validate_saml_assertion(payload) is False


# --- CORS --------------------------------------------------------------------
def _preflight(client, origin):
    return client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


@pytest.mark.parametrize("origin", [
    "https://evil.onrender.com", "https://evil.vercel.app", "https://evil.fly.dev",
])
def test_shared_hosting_domains_are_not_wildcarded(origin):
    from fastapi.testclient import TestClient
    from src.main import cors_app
    assert "access-control-allow-origin" not in _preflight(TestClient(cors_app), origin).headers


def test_extra_origin_comes_only_from_env(monkeypatch):
    monkeypatch.setenv("VISHAP_CORS_ORIGINS", "https://ui.example.com/, *")
    import src.main as m
    m = importlib.reload(m)
    from fastapi.testclient import TestClient
    c = TestClient(m.cors_app)
    assert _preflight(c, "https://ui.example.com").headers.get("access-control-allow-origin") == "https://ui.example.com"
    assert "access-control-allow-origin" not in _preflight(c, "https://other.example.com").headers
    monkeypatch.delenv("VISHAP_CORS_ORIGINS")
    importlib.reload(m)


# --- rate limiter ------------------------------------------------------------
def test_forwarded_header_ignored_by_default(monkeypatch):
    monkeypatch.delenv("VISHAP_TRUSTED_PROXY_HOPS", raising=False)
    assert rate_limit.client_ip(_request("1.1.1.1", host="10.0.0.1")) == "10.0.0.1"


def test_forwarded_header_counted_from_the_right(monkeypatch):
    monkeypatch.setenv("VISHAP_TRUSTED_PROXY_HOPS", "1")
    # a spoofed leftmost value must not win; the proxy appended the real client last
    assert rate_limit.client_ip(_request("6.6.6.6, 203.0.113.9")) == "203.0.113.9"


def test_bad_hops_value_falls_back(monkeypatch):
    monkeypatch.setenv("VISHAP_TRUSTED_PROXY_HOPS", "abc")
    assert rate_limit.client_ip(_request("1.1.1.1", host="10.0.0.2")) == "10.0.0.2"


def test_limit_and_sweep():
    rate_limit._BUCKETS.clear()
    for _ in range(rate_limit.LIMIT_ANALYZE):
        rate_limit._check("analyze:t", rate_limit.LIMIT_ANALYZE)
    with pytest.raises(HTTPException) as e:
        rate_limit._check("analyze:t", rate_limit.LIMIT_ANALYZE)
    assert e.value.status_code == 429
    rate_limit._sweep(10**12)  # everything is older than the window
    assert not rate_limit._BUCKETS


# --- user-supplied LLM key ---------------------------------------------------
def test_require_user_key_blocks_server_key_fallback(monkeypatch):
    from src.llm import client
    monkeypatch.setenv("VISHAP_REQUIRE_USER_LLM_KEY", "1")
    monkeypatch.setenv("CUSTOM_LLM_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("CUSTOM_LLM_KEY", "operator-secret")
    client.set_api_key(None)
    out = client.chat("sys", "user")
    assert out["mode"] == "error" and "X-LLM-Api-Key" in out["text"]
    assert "operator-secret" not in str(out)


def test_user_key_is_used_when_provided(monkeypatch):
    from src.llm import client, custom_client
    seen = {}

    class Fake:
        def __init__(self, api_key=None, **kw):
            seen["key"] = api_key
        def chat(self, *a, **kw):
            return {"text": "ok", "tokens_in": 1, "tokens_out": 1, "model": "m", "mode": "custom"}
        def close(self):
            pass

    monkeypatch.setattr(custom_client, "CustomClient", Fake)
    monkeypatch.setenv("VISHAP_REQUIRE_USER_LLM_KEY", "1")
    client.set_api_key("user-key")
    try:
        assert client.chat("s", "u")["text"] == "ok"
    finally:
        client.set_api_key(None)
    assert seen["key"] == "user-key"


def test_async_chat_passes_the_callers_key_into_the_worker_thread(monkeypatch):
    import asyncio
    from src.llm import client, async_client
    got = {}

    def fake(system, user, temperature, max_tokens, api_key=None):
        got["key"] = api_key
        return {"text": "ok"}

    monkeypatch.setattr(client, "_chat_custom", fake)
    client.set_api_key("user-key")
    try:
        asyncio.run(async_client.async_chat("s", "u"))
    finally:
        client.set_api_key(None)
    assert got["key"] == "user-key"


def test_analyze_endpoints_demand_a_key_in_user_key_mode(monkeypatch):
    from fastapi.testclient import TestClient
    from src.main import app
    monkeypatch.setenv("VISHAP_REQUIRE_USER_LLM_KEY", "1")
    c = TestClient(app)
    for path, body in [
        ("/analyze", {"material": "x = 1", "filename": "a.py"}),
        ("/analyze/async", {"material": "x = 1", "filename": "a.py"}),
        ("/analyze/batch", {"items": [{"material": "x = 1", "filename": "a.py"}]}),
    ]:
        r = c.post(path, json=body)
        assert r.status_code in (401, 403), (path, r.status_code, r.text)
