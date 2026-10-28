"""Who may talk to the server: Host and Origin checks, and the bearer token."""

from __future__ import annotations

import hmac
from urllib.parse import urlsplit


def host_ok(host_header: str | None, origin_header: str | None, host_names: set[str]) -> bool:
    """Host must be one of ours; an Origin, when present, must be ours too.

    This is what stops a page on another site (or a DNS-rebinding trick) from spending
    the user's model key through their browser.
    """
    host = (host_header or "").rsplit(":", 1)[0].strip("[]").lower()
    if host not in host_names:
        return False
    if origin_header:
        if (urlsplit(origin_header).hostname or "").lower() not in host_names:
            return False
    return True


def token_ok(authorization: str | None, token: str | None) -> bool:
    """No token configured: open (loopback only). Otherwise `Bearer <token>`, compared safely."""
    if not token:
        return True
    got = authorization or ""
    return got.startswith("Bearer ") and hmac.compare_digest(got[7:], token)
