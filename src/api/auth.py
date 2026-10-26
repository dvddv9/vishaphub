import hmac
# -*- coding: utf-8 -*-
"""API-key authentication (dogfood P0 fix).

Dogfood finding: POST /analyze, /history/clear, /mode were open
to any client on 0.0.0.0:5001.

Behavior:
- If CONVEYOR_API_KEY is set in .env -> require X-API-Key header.
- If CONVEYOR_API_KEY is NOT set -> API works ONLY on 127.0.0.1
  (see main.py uvicorn.run binding).

Since v6.5 a second credential is accepted: a tenant key issued by
``scripts/generate_key.py`` for customers billed by bank transfer. That path is
**opt-in** via ``VISHAP_TENANT_KEYS=true`` because it turns every rejected request
into a database lookup; with the flag off the behaviour is byte-for-byte the old
one.
"""
import os

from fastapi import Header, HTTPException, status

from src.config import CONVEYOR_API_KEY

#: Static key from .env. Read through src.config, which loads .env at import —
#: reading os.environ here directly raced with that load and could pin an empty
#: value depending on module import order.
API_KEY = (CONVEYOR_API_KEY or "").strip()

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _tenant_keys_enabled() -> bool:
    """True when tenant-issued API keys are accepted alongside the static key."""
    return os.getenv("VISHAP_TENANT_KEYS", "").strip().lower() in _TRUE_VALUES


async def verify_api_key(x_api_key: str = Header(default="")) -> None:
    """FastAPI dependency: verify X-API-Key header.

    Order of checks:

    1. the static ``CONVEYOR_API_KEY`` matches — accepted without touching the
       database;
    2. ``VISHAP_TENANT_KEYS`` is on — delegate to the tenant lookup, which also
       enforces status and expiry;
    3. no static key configured (dev mode) — allow, since main.py binds to
       127.0.0.1;
    4. otherwise reject.
    """
    if x_api_key and API_KEY and hmac.compare_digest(x_api_key, API_KEY):
        return

    if _tenant_keys_enabled():
        from src.auth.middleware import verify_tenant_api_key

        # Raises 401 (missing / invalid / inactive / expired).
        await verify_tenant_api_key(x_api_key)
        return

    if not API_KEY:
        # Same documented test switch as the import-time gate in src/main.py:
        # VISHAP_ALLOW_NO_KEY=1 means "trusted loopback-only test environment".
        if os.getenv("VISHAP_ALLOW_NO_KEY", "").strip().lower() in _TRUE_VALUES:
            return
        raise RuntimeError("CONVEYOR_API_KEY/API_KEY is required (fail-closed)")

    if os.getenv("VISHAP_PUBLIC_DEMO", "").strip().lower() in _TRUE_VALUES:
        # Open demo: the server's own model pays for the call, so the caller needs
        # no key. The daily limiter on /analyze is what bounds the spend.
        return

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header required",
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid API key",
    )


def is_auth_enabled() -> bool:
    """True if CONVEYOR_API_KEY is set."""
    return bool(API_KEY)
