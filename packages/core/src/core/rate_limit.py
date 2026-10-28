"""Token-bucket limits: one per client, one global, no framework.

Two limits, two purposes:

* the **per-client** limit stops one caller from taking the queue;
* the **global** limit stops the deployment from spending more than the owner
  allowed for the day.

They are independent. The effective rule is the stricter one — not the average,
not «both». A caller that passes both passes; anything else waits.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Bucket:
    capacity: int
    refill_seconds: float
    tokens: float = 0.0
    last: float = field(default_factory=time.monotonic)

    def take(self, now: float | None = None, cost: float = 1.0) -> bool:
        now = time.monotonic() if now is None else now
        elapsed = max(0.0, now - self.last)
        if self.refill_seconds > 0:
            self.tokens = min(float(self.capacity), self.tokens + elapsed / self.refill_seconds)
        self.last = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


@dataclass
class LimitDecision:
    allowed: bool
    reason: str = ""
    retry_after: int = 0


class Limiter:
    """Per-client buckets plus one global bucket. Thread-unsafe by design: pass a lock."""

    def __init__(self, per_client: int, per_client_seconds: float, global_cap: int, global_seconds: float):
        self.per_client = per_client
        self.per_client_seconds = per_client_seconds
        self.global_bucket = Bucket(global_cap, global_seconds, tokens=float(global_cap))
        self.clients: dict[str, Bucket] = {}

    def allow(self, client: str) -> LimitDecision:
        if self.per_client > 0:
            bucket = self.clients.get(client)
            if bucket is None:
                bucket = Bucket(self.per_client, self.per_client_seconds, tokens=float(self.per_client))
                self.clients[client] = bucket
            if not bucket.take():
                return LimitDecision(False, "per-client limit", int(self.per_client_seconds))

        if self.global_bucket.capacity > 0 and not self.global_bucket.take():
            return LimitDecision(False, "global limit", int(self.global_bucket.refill_seconds))

        return LimitDecision(True)
