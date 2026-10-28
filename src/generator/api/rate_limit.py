"""Limits on the API: one generate run at a time, and a request limit per client address.

The analog of Vishap's `api/rate_limit.py`. A run costs model tokens, so `RUN_LOCK` lets one generate run go at
a time. `RateLimiter` is a sliding window per client IP (the socket address; a proxy header is never trusted,
so behind a reverse proxy the limit applies to the proxy as a whole: set it there too).
"""

import collections
import os
import threading
import time

RUN_LOCK = threading.Lock()
DEFAULT_PER_MINUTE = 30


def per_minute() -> int:
    """GENERATOR_RATE_LIMIT: requests per minute per address; 0 turns the limit off."""
    try:
        return max(0, int(os.environ.get("GENERATOR_RATE_LIMIT", DEFAULT_PER_MINUTE)))
    except ValueError:
        return DEFAULT_PER_MINUTE


class RateLimiter:
    def __init__(self, limit: int, window: float = 60.0, clock=time.monotonic):
        self.limit, self.window, self._clock = limit, window, clock
        self._hits: dict[str, collections.deque] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> float:
        """0.0 when the request may go on, else the seconds until it may."""
        if self.limit <= 0:
            return 0.0
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, collections.deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(0.1, self.window - (now - hits[0]))
            hits.append(now)
            if len(self._hits) > 1000:                       # forget addresses that went quiet
                for k in [k for k, h in self._hits.items() if not h or now - h[-1] >= self.window]:
                    del self._hits[k]
            return 0.0
