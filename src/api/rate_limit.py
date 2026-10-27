# -*- coding: utf-8 -*-
"""Simple in-memory rate limiter (dogfood P0 fix).

Dogfood finding: no rate limiting on /analyze -> any client could
exhaust the local LLM endpoint (one model, no queue of its own).

Limits (per IP):
- 10 requests / minute for /analyze, /analyze/batch
- 30 requests / minute for /history, /mode

Behind a reverse proxy (Render, Fly, nginx) ``request.client.host`` is the proxy,
so all clients would share one bucket. Set ``VISHAP_TRUSTED_PROXY_HOPS`` to the
number of trusted proxies in front of the app (Render: 1) and the client IP is
taken from ``X-Forwarded-For`` counted from the RIGHT, where the trusted proxies
append it. Default 0 ignores the header (it is client-controlled when no proxy
strips it). State is in-memory per process.
"""
import os
import time
from collections import defaultdict, deque
from fastapi import Request, HTTPException, status


_BUCKETS = defaultdict(deque)

LIMIT_ANALYZE = 10
LIMIT_READ = 30
WINDOW_SECONDS = 60
_SWEEP_EVERY = 256
_calls = 0


def _sweep(now: float) -> None:
    """Drop buckets whose newest hit left the window (bounds memory)."""
    for key in [k for k, q in _BUCKETS.items() if not q or q[-1] < now - WINDOW_SECONDS]:
        del _BUCKETS[key]


def _check(key: str, limit: int) -> None:
    global _calls
    now = time.time()
    _calls += 1
    if _calls % _SWEEP_EVERY == 0:
        _sweep(now)
    bucket = _BUCKETS[key]

    while bucket and bucket[0] < now - WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded: {} req / {}s".format(limit, WINDOW_SECONDS),
        )

    bucket.append(now)


def client_ip(request: Request) -> str:
    """Client address; honours X-Forwarded-For only for trusted proxy hops."""
    try:
        hops = int(os.getenv("VISHAP_TRUSTED_PROXY_HOPS", "0"))
    except ValueError:
        hops = 0
    if hops > 0:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"


async def rate_limit_analyze(request: Request) -> None:
    _check("analyze:" + client_ip(request), LIMIT_ANALYZE)


async def rate_limit_read(request: Request) -> None:
    _check("read:" + client_ip(request), LIMIT_READ)


# ---------------------------------------------------------------- daily cap --
# The public demo runs on the server's own model key, so the day cap — not the
# minute cap — is what bounds the bill. Per client IP, reset at 00:00 UTC.
# VISHAP_DAILY_LIMIT           analyses per IP per day (default 7)
# VISHAP_DAILY_LIMIT_GLOBAL    ceiling for ALL visitors together (default 30; 0 = off)
def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


LIMIT_DAILY = _env_int("VISHAP_DAILY_LIMIT", 7)
_DAY_COUNTS: dict[tuple[str, str], int] = {}


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _check_daily(key: str, limit: int, peek_only: bool = False) -> None:
    today = _today()
    # Cheap sweep: a day change is the only thing that can invalidate entries.
    if any(day != today for _k, day in _DAY_COUNTS):
        for old in [k for k in _DAY_COUNTS if k[1] != today]:
            del _DAY_COUNTS[old]
    entry = (key, today)
    used = _DAY_COUNTS.get(entry, 0)
    if used >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily limit reached: {limit} analyses per day. Try again tomorrow (UTC).",
        )
    if not peek_only:
        _DAY_COUNTS[entry] = used + 1


def _server_key_only() -> bool:
    from src.llm.client import server_key_only
    return server_key_only()


async def rate_limit_daily(request: Request) -> None:
    """Per-visitor day cap (by client IP) AND a global ceiling for everybody.

    A caller who brings their own LLM key (``X-LLM-Api-Key``) pays for the call
    themselves, so the operator's caps do not apply to them — only the per-minute
    limiter above still does.

    Not in server-key-only mode (VISHAP_SERVER_KEY_ONLY): there the header is ignored
    and the call runs on the operator's key, so sending a junk key must not lift the caps.
    """
    if (request.headers.get("x-llm-api-key") or "").strip() and not _server_key_only():
        return
    global_cap = _env_int("VISHAP_DAILY_LIMIT_GLOBAL", 30)
    if global_cap:
        _check_daily("daily:global", global_cap, peek_only=True)
    if LIMIT_DAILY:
        _check_daily("daily:" + client_ip(request), LIMIT_DAILY)
    if global_cap:
        _check_daily("daily:global", global_cap)
