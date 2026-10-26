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
