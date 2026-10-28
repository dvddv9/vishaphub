# -*- coding: utf-8 -*-
"""Clerk JWT verification via JWKS (v6.1)."""
import os
import time
from typing import Any

import httpx
import jwt


class AuthError(Exception):
    """Raised when a Clerk JWT cannot be verified."""


#: url -> (fetched_at, document). Refetched after _JWKS_TTL seconds, and once (at most every
#: _JWKS_MIN_REFRESH seconds) when a token names an unknown ``kid``: a Clerk key rotation
#: must not need a restart.
_jwks_cache: dict[str, Any] = {}
_JWKS_TTL = 3600
_JWKS_MIN_REFRESH = 60


def is_configured() -> bool:
    """True when Clerk can verify tokens (a JWKS URL is available).

    ``CLERK_SECRET_KEY`` alone is not enough to verify an RS256 token — the
    public keys come from the JWKS document. Endpoints that depend on
    :func:`verify_jwt` therefore answer 401 with "Clerk not configured" rather
    than failing with a 500 when the deployment has no Clerk credentials.
    """
    return bool(os.getenv("CLERK_JWKS_URL", "").strip())


def _fetch_jwks() -> dict:
    """Fetch (and cache) the Clerk JWKS document."""
    url = os.getenv("CLERK_JWKS_URL", "").strip()
    if not url:
        raise AuthError("Clerk not configured")
    hit = _jwks_cache.get(url)
    now = time.monotonic()
    if hit is not None and now - hit[0] < _JWKS_TTL:
        return hit[1]
    try:
        r = httpx.get(url, timeout=10)
        r.raise_for_status()
        doc = r.json()
    except Exception:
        if hit is not None:  # Clerk unreachable: keep serving the last known keys
            return hit[1]
        raise
    _jwks_cache[url] = (now, doc)
    return doc


def verify_jwt(token: str) -> dict:
    """Verify a Clerk RS256 JWT against JWKS; return its claims."""
    if not is_configured():
        raise AuthError("Clerk not configured")

    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise AuthError("No kid in token header")

        jwks = _fetch_jwks()
        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if not key_data:
            url = os.getenv("CLERK_JWKS_URL", "").strip()
            hit = _jwks_cache.get(url)
            if hit is None or time.monotonic() - hit[0] >= _JWKS_MIN_REFRESH:
                _jwks_cache.pop(url, None)
                jwks = _fetch_jwks()
                key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if not key_data:
            raise AuthError(f"Unknown kid: {kid}")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
        # CLERK_ISSUER (your Frontend API URL) pins the issuer; CLERK_AUTHORIZED_PARTIES
        # (comma-separated origins) pins ``azp``. Unset = not enforced, as before.
        issuer = os.getenv("CLERK_ISSUER", "").strip()
        claims = jwt.decode(token, public_key, algorithms=["RS256"], **({"issuer": issuer} if issuer else {}))

        if "sub" not in claims:
            raise AuthError("Missing 'sub' claim")
        parties = [p.strip() for p in os.getenv("CLERK_AUTHORIZED_PARTIES", "").split(",") if p.strip()]
        if parties and claims.get("azp") not in parties:
            raise AuthError("Unauthorized party")
        return claims
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expired")
    except jwt.InvalidSignatureError:
        raise AuthError("Invalid signature")
    except jwt.PyJWTError as e:
        raise AuthError(f"JWT error: {e}")
