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

    def fake(system, user, temperature, max_tokens, api_key=None, target=None):
        got["key"] = api_key
        got["target"] = target
        return {"text": "ok"}

    monkeypatch.setattr(client, "_chat_custom", fake)
    client.set_api_key("user-key")
    try:
        client.set_llm_target(("https://api.anthropic.com/v1", "claude-sonnet-5-5"))
        asyncio.run(async_client.async_chat("s", "u"))
    finally:
        client.set_api_key(None)
        client.set_llm_target(None)
    assert got["key"] == "user-key"
    assert got["target"] == ("https://api.anthropic.com/v1", "claude-sonnet-5-5")


def _auth_headers():
    from src.config import CONVEYOR_API_KEY
    return {"X-API-Key": CONVEYOR_API_KEY} if CONVEYOR_API_KEY else {}


def test_batch_still_demands_a_key_in_user_key_mode(monkeypatch):
    """Batch has no rules-only mode: without the caller's key it is refused."""
    from fastapi.testclient import TestClient
    from src.main import app
    monkeypatch.setenv("VISHAP_REQUIRE_USER_LLM_KEY", "1")
    r = TestClient(app).post("/analyze/batch", headers=_auth_headers(),
                             json={"items": [{"material": "x = 1", "filename": "a.py"}]})
    assert r.status_code in (401, 403), (r.status_code, r.text)


def test_keyless_visitor_gets_the_rules_only_report(monkeypatch):
    """No key in user-key mode -> built-in rules, never a 401 and never the server's key."""
    from fastapi.testclient import TestClient
    from src.main import app
    monkeypatch.setenv("VISHAP_REQUIRE_USER_LLM_KEY", "1")
    called = []
    import src.pipeline.async_stages as stages
    monkeypatch.setattr(stages, "async_chat", lambda *a, **k: called.append(1))
    c = TestClient(app)
    body = {"material": 'import os\nos.system("rm -rf " + name)\ncur.execute("SELECT * FROM t WHERE a=\'" + a + "\'")\n',
            "filename": "vuln.py"}

    r = c.post("/analyze/async", headers=_auth_headers(), json=body)
    assert r.status_code == 200, r.text
    job = r.json()["job_id"]
    rep = c.get(f"/report/{job}", headers=_auth_headers())
    assert rep.status_code == 200, rep.text
    data = rep.json()
    assert data["mode"] == "static"
    assert "CWE-89" in data["audit"]["cwe_ids"]
    assert "Static analysis" in data["final_markdown"]
    assert not called, "the LLM must not be called without the caller's key"

    r = c.post("/analyze", headers=_auth_headers(), json=body)
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "static"


def test_providers_endpoint_reports_user_key_mode(monkeypatch):
    from fastapi.testclient import TestClient
    from src.main import app
    monkeypatch.setenv("VISHAP_REQUIRE_USER_LLM_KEY", "1")
    r = TestClient(app).get("/providers", headers=_auth_headers())
    assert r.status_code == 200 and r.json()["requires_user_key"] is True
    monkeypatch.delenv("VISHAP_REQUIRE_USER_LLM_KEY")
    assert TestClient(app).get("/providers", headers=_auth_headers()).json()["requires_user_key"] is False


# --- provider allow-list -------------------------------------------------------
def test_provider_resolves_only_from_the_server_table(monkeypatch):
    from src.llm import providers
    monkeypatch.delenv("VISHAP_ALLOWED_PROVIDERS", raising=False)
    assert providers.resolve(None, None) is None
    assert providers.resolve("", "x") is None
    assert providers.resolve("Anthropic", None) == ("https://api.anthropic.com/v1", "claude-sonnet-5-5")
    assert providers.resolve("deepseek", "deepseek-reasoner") == ("https://api.deepseek.com/v1", "deepseek-reasoner")


@pytest.mark.parametrize("bad", [
    "https://evil.example/v1", "evil", "http://127.0.0.1:8000", "../x", "deepseek@evil.com",
])
def test_provider_rejects_urls_and_unknown_ids(bad):
    from src.llm import providers
    with pytest.raises(providers.ProviderError):
        providers.resolve(bad, None)


@pytest.mark.parametrize("bad_model", ["a b", "x;rm", "", "../..", "m" * 200, "m\nx"])
def test_provider_rejects_malformed_models(bad_model):
    from src.llm import providers
    if bad_model == "":
        assert providers.resolve("openai", bad_model)[1] == "gpt-4o-mini"  # empty -> default
        return
    with pytest.raises(providers.ProviderError):
        providers.resolve("openai", bad_model)


def test_allowed_providers_env_narrows_the_list(monkeypatch):
    from src.llm import providers
    monkeypatch.setenv("VISHAP_ALLOWED_PROVIDERS", "deepseek, anthropic")
    assert [p["id"] for p in providers.list_providers()] == ["deepseek", "anthropic"]
    with pytest.raises(providers.ProviderError):
        providers.resolve("openai", None)


def test_operator_key_is_never_sent_to_a_caller_chosen_provider(monkeypatch):
    from src.llm import client
    monkeypatch.setenv("CUSTOM_LLM_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("CUSTOM_LLM_KEY", "operator-secret")
    client.set_api_key(None)
    client.set_llm_target(("https://api.openai.com/v1", "gpt-4o-mini"))
    try:
        out = client.chat("s", "u")
    finally:
        client.set_llm_target(None)
    assert out["mode"] == "error"
    assert "operator-secret" not in str(out)


def test_chosen_provider_and_user_key_reach_the_client(monkeypatch):
    from src.llm import client, custom_client
    seen = {}

    class Fake:
        def __init__(self, base_url=None, api_key=None, model=None, **kw):
            seen.update(url=base_url, key=api_key, model=model)
        def chat(self, *a, **kw):
            return {"text": "ok", "tokens_in": 1, "tokens_out": 1, "model": "m", "mode": "custom"}
        def close(self):
            pass

    monkeypatch.setattr(custom_client, "CustomClient", Fake)
    client.set_api_key("user-key")
    client.set_llm_target(("https://api.anthropic.com/v1", "claude-sonnet-5-5"))
    try:
        assert client.chat("s", "u")["text"] == "ok"
    finally:
        client.set_api_key(None)
        client.set_llm_target(None)
    assert seen == {"url": "https://api.anthropic.com/v1", "key": "user-key", "model": "claude-sonnet-5-5"}


# --- /llm/config -------------------------------------------------------------
def test_llm_config_cannot_be_rewritten_in_user_key_mode(monkeypatch):
    import os
    from fastapi.testclient import TestClient
    from src.main import app
    monkeypatch.setenv("VISHAP_REQUIRE_USER_LLM_KEY", "1")
    before = os.environ.get("CUSTOM_LLM_URL")
    c = TestClient(app)
    r = c.post("/llm/config", json={
        "provider": "custom", "custom_url": "https://evil.example/v1",
        "custom_model": "m", "custom_key": "k",
    })
    assert r.status_code in (401, 403), r.text
    assert os.environ.get("CUSTOM_LLM_URL") == before
    g = c.get("/llm/config")
    if g.status_code == 200:
        assert g.json()["locked"] is True and g.json()["has_custom_key"] is False


def test_llm_config_router_requires_the_api_key():
    from src.api import llm_config
    deps = [d.dependency.__name__ for d in llm_config.router.dependencies]
    assert "verify_api_key" in deps


# --- providers that reject `temperature` / `max_tokens` -----------------------
def _fake_response(status, body):
    class R:
        status_code = status
        text = body
        def json(self):
            import json
            return json.loads(body)
    return R()


def test_custom_client_retries_without_temperature(monkeypatch):
    from src.llm import custom_client
    custom_client._NO_TEMPERATURE.clear()
    sent = []
    ok = '{"choices":[{"message":{"content":"hi"}}],"usage":{}}'
    bad = '{"error":{"message":"`temperature` is deprecated for this model."}}'

    def fake_post(url, headers=None, data=None, timeout=None):
        import json
        body = json.loads(data.decode("utf-8"))
        sent.append(body)
        return _fake_response(400 if "temperature" in body else 200, bad if "temperature" in body else ok)

    monkeypatch.setattr(custom_client.requests, "post", fake_post)
    c = custom_client.CustomClient(base_url="https://x.invalid/v1", api_key="k", model="m1")
    assert c.chat("u", "s", temperature=0.2)["text"] == "hi"
    assert "temperature" in sent[0] and "temperature" not in sent[1]
    # remembered: the next call does not send it at all
    sent.clear()
    assert c.chat("u", "s", temperature=0.2)["text"] == "hi"
    assert len(sent) == 1 and "temperature" not in sent[0]
    custom_client._NO_TEMPERATURE.clear()


def test_custom_client_switches_to_max_completion_tokens(monkeypatch):
    from src.llm import custom_client
    custom_client._USE_MAX_COMPLETION_TOKENS.clear()
    ok = '{"choices":[{"message":{"content":"yo"}}],"usage":{}}'
    bad = '{"error":{"message":"Unsupported parameter: use max_completion_tokens instead."}}'

    def fake_post(url, headers=None, data=None, timeout=None):
        import json
        body = json.loads(data.decode("utf-8"))
        return _fake_response(400, bad) if "max_tokens" in body else _fake_response(200, ok)

    monkeypatch.setattr(custom_client.requests, "post", fake_post)
    c = custom_client.CustomClient(base_url="https://y.invalid/v1", api_key="k", model="m2")
    assert c.chat("u", "s")["text"] == "yo"
    custom_client._USE_MAX_COMPLETION_TOKENS.clear()


# --- output-token ceiling / rate limits ------------------------------------------
def test_custom_client_clamps_max_tokens_to_the_providers_ceiling(monkeypatch):
    from src.llm import custom_client
    custom_client._MAX_OUT_CAP.clear()
    sent = []
    ok = '{"choices":[{"message":{"content":"ok"}}],"usage":{}}'
    bad = '{"error":{"message":"Invalid max_tokens value, the valid range of max_tokens is [1, 8192]"}}'

    def fake_post(url, headers=None, data=None, timeout=None):
        import json
        body = json.loads(data.decode("utf-8"))
        sent.append(body["max_tokens"])
        return _fake_response(400, bad) if body["max_tokens"] > 8192 else _fake_response(200, ok)

    monkeypatch.setattr(custom_client.requests, "post", fake_post)
    c = custom_client.CustomClient(base_url="https://z.invalid/v1", api_key="k", model="deepseek-chat")
    assert c.chat("u", "s", max_tokens=16000)["text"] == "ok"
    assert sent == [16000, 8192]
    sent.clear()
    assert c.chat("u", "s", max_tokens=16000)["text"] == "ok"
    assert sent == [8192], "the learned ceiling is applied up front"
    custom_client._MAX_OUT_CAP.clear()


def test_custom_client_retries_a_rate_limit_then_succeeds(monkeypatch):
    from src.llm import custom_client
    monkeypatch.setattr(custom_client._time, "sleep", lambda s: None)
    calls = []
    ok = '{"choices":[{"message":{"content":"fine"}}],"usage":{}}'

    class Limited:
        status_code = 429
        text = "rate limited"
        headers = {"retry-after": "1"}

    def fake_post(url, headers=None, data=None, timeout=None):
        calls.append(1)
        return Limited() if len(calls) == 1 else _fake_response(200, ok)

    monkeypatch.setattr(custom_client.requests, "post", fake_post)
    c = custom_client.CustomClient(base_url="https://r.invalid/v1", api_key="k", model="m3")
    assert c.chat("u", "s")["text"] == "fine" and len(calls) == 2


def test_output_cap_parser():
    from src.llm.custom_client import _parse_output_cap
    assert _parse_output_cap("the valid range of max_tokens is [1, 8192]") == 8192
    assert _parse_output_cap("max_tokens must be at most 4096") == 4096
    assert _parse_output_cap("something unrelated") is None


# --- keys never leak into error text ---------------------------------------------
def test_scrub_removes_the_key_and_key_shaped_strings():
    from src.llm._scrub import scrub
    key = "sk-ant-usr-abcdefghijklmnopqrstuvwxyz0123456789"
    out = scrub(f"401 Incorrect API key provided: {key}; Bearer abcdefghijklmnopqrstu", key)
    assert key not in out and "abcdefghijklmnopqrstu" not in out and "[key hidden]" in out
    assert scrub("plain error", "k") == "plain error"          # too short to treat as a secret


def test_provider_error_that_echoes_the_key_is_scrubbed(monkeypatch):
    from src.llm import custom_client
    key = "gsk_SECRETSECRETSECRET1234"
    body = '{"error":{"message":"Invalid API Key: %s"}}' % key
    monkeypatch.setattr(custom_client.requests, "post", lambda *a, **k: _fake_response(401, body))
    c = custom_client.CustomClient(base_url="https://q.invalid/v1", api_key=key, model="m")
    try:
        c.chat("u", "s")
    except custom_client.CustomError as e:
        assert key not in str(e) and "[key hidden]" in str(e)
    else:
        raise AssertionError("expected CustomError")


# --- server-key-only mode (built-in DeepSeek key, no other LLMs) -------------------
def test_server_key_only_ignores_caller_llm_choices(monkeypatch):
    from src.llm import client
    from src.main import _apply_llm_request
    monkeypatch.setenv("VISHAP_SERVER_KEY_ONLY", "1")
    monkeypatch.setenv("VISHAP_REQUIRE_USER_LLM_KEY", "1")  # overridden
    assert client.require_user_key() is False
    assert _apply_llm_request("user-key", "openai", "gpt-4o-mini") == (None, None)
    assert client.get_api_key() is None and client.get_llm_target() is None
    # an unknown provider is ignored too, not a 400
    assert _apply_llm_request("k", "evil", None) == (None, None)


def test_server_key_only_providers_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from src.main import app
    monkeypatch.setenv("VISHAP_SERVER_KEY_ONLY", "1")
    data = TestClient(app).get("/providers", headers=_auth_headers()).json()
    assert data["server_key_only"] is True and data["providers"] == []
    assert data["requires_user_key"] is False


def test_server_key_only_uses_the_servers_key(monkeypatch):
    from src.llm import client, custom_client
    seen = {}

    class Fake:
        def __init__(self, api_key=None, base_url=None, model=None, **kw):
            seen.update(key=api_key, url=base_url)
        def chat(self, *a, **kw):
            return {"text": "ok", "tokens_in": 1, "tokens_out": 1, "model": "m", "mode": "custom"}
        def close(self):
            pass

    monkeypatch.setattr(custom_client, "CustomClient", Fake)
    monkeypatch.setenv("VISHAP_SERVER_KEY_ONLY", "1")
    client.set_api_key(None)
    client.set_llm_target(None)
    assert client.chat("s", "u")["text"] == "ok"
    assert seen == {"key": None, "url": None}  # CustomClient falls back to CUSTOM_LLM_*


def test_server_key_only_without_a_server_key_falls_back_to_rules(monkeypatch):
    from src.main import _is_static_only
    monkeypatch.setenv("VISHAP_SERVER_KEY_ONLY", "1")
    monkeypatch.delenv("CUSTOM_LLM_KEY", raising=False)
    assert _is_static_only(None) is True
    monkeypatch.setenv("CUSTOM_LLM_KEY", "k")
    assert _is_static_only(None) is False


# --- daily cap: per visitor (IP), default 7 -----------------------------------------
def test_daily_limit_is_per_ip_and_defaults_to_seven(monkeypatch):
    import asyncio
    monkeypatch.delenv("VISHAP_DAILY_LIMIT", raising=False)
    monkeypatch.delenv("VISHAP_DAILY_LIMIT_GLOBAL", raising=False)
    importlib.reload(rate_limit)
    assert rate_limit.LIMIT_DAILY == 7
    rate_limit._DAY_COUNTS.clear()
    a, b = _request(host="10.0.0.1"), _request(host="10.0.0.2")
    for _ in range(7):
        asyncio.run(rate_limit.rate_limit_daily(a))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(rate_limit.rate_limit_daily(a))
    assert exc.value.status_code == 429 and "7 analyses" in exc.value.detail
    asyncio.run(rate_limit.rate_limit_daily(b))  # another visitor is unaffected


def test_daily_global_ceiling_is_optional(monkeypatch):
    import asyncio
    monkeypatch.setenv("VISHAP_DAILY_LIMIT_GLOBAL", "2")
    importlib.reload(rate_limit)
    rate_limit._DAY_COUNTS.clear()
    for host in ("10.0.0.1", "10.0.0.2"):
        asyncio.run(rate_limit.rate_limit_daily(_request(host=host)))
    with pytest.raises(HTTPException):
        asyncio.run(rate_limit.rate_limit_daily(_request(host="10.0.0.3")))
    monkeypatch.delenv("VISHAP_DAILY_LIMIT_GLOBAL")
    importlib.reload(rate_limit)
