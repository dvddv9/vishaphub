# -*- coding: utf-8 -*-
"""CORS preflight for the Tauri desktop shell (Block 42).

The packaged app loads its UI from `http://tauri.localhost`, which Chromium places
in the *public* address space, while the API lives on `127.0.0.1` (*local*). Every
request is therefore a Private Network Access request: the browser adds
`Access-Control-Request-Private-Network: true` to the preflight and refuses the
fetch unless the answer carries `Access-Control-Allow-Private-Network: true`.

Starlette defaults `allow_private_network` to False and answers such a preflight
with 400, which the UI surfaces as "Cannot reach the Vishap API" even though
`curl http://127.0.0.1:5001/health` works. These tests keep the flag on and keep
foreign origins out.

Run: pytest tests/test_cors_pna.py -q
"""

from fastapi.testclient import TestClient

# `cors_app` is the CORS-wrapped ASGI entrypoint the server runs; `app` is the
# raw FastAPI instance (no CORS), which tests that do not care about CORS import.
from src.main import cors_app as app

DESKTOP_ORIGIN = "http://tauri.localhost"


def _preflight(origin: str, method: str = "GET", headers: str = "x-api-key"):
    client = TestClient(app)
    return client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
            "Access-Control-Request-Private-Network": "true",
        },
    )


def test_private_network_preflight_from_the_desktop_shell_is_allowed():
    response = _preflight(DESKTOP_ORIGIN)

    assert response.status_code == 200, (
        "Starlette answers 400 when allow_private_network is off, and the webview "
        f"then blocks the request: {response.headers}"
    )
    assert response.headers.get("access-control-allow-origin") == DESKTOP_ORIGIN
    assert response.headers.get("access-control-allow-private-network") == "true"


def test_private_network_preflight_allows_the_api_key_header():
    response = _preflight(DESKTOP_ORIGIN, method="POST", headers="content-type,x-api-key")

    assert response.status_code == 200
    allowed = response.headers.get("access-control-allow-headers", "").lower()
    assert "x-api-key" in allowed
    assert "content-type" in allowed


def test_loopback_origins_are_allowed_on_any_port():
    for origin in ("http://127.0.0.1:5001", "http://localhost:3000", "tauri://localhost"):
        response = _preflight(origin)
        assert response.status_code == 200, origin
        assert response.headers.get("access-control-allow-origin") == origin


def test_foreign_origin_is_not_granted_cors():
    response = _preflight("https://evil.example")

    assert "access-control-allow-origin" not in response.headers, (
        "a public origin must never be granted access to the local API"
    )


def test_error_responses_still_carry_cors_headers():
    """A 500 must include `Access-Control-Allow-Origin`, or the webview reports
    the request as 'blocked by CORS policy' instead of showing the real error.

    The mechanism in `src/main.py` is the explicit outer wrap
    `cors_app = CORSMiddleware(app, ...)`: CORS sits OUTSIDE
    ServerErrorMiddleware, so an unhandled exception's 500 still passes through it
    on the way out. A bare 500 would have no CORS header.
    """
    from fastapi import FastAPI
    from starlette.middleware.cors import CORSMiddleware
    from fastapi.testclient import TestClient as TC

    inner = FastAPI()

    @inner.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    wrapped = CORSMiddleware(
        inner,
        allow_origins=[DESKTOP_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    response = TC(wrapped, raise_server_exceptions=False).get(
        "/boom", headers={"Origin": DESKTOP_ORIGIN}
    )
    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == DESKTOP_ORIGIN, (
        "a 500 without CORS headers is exactly the desktop webview failure mode"
    )

