"""Limits: two buckets, and the stricter one decides."""
from core.rate_limit import Bucket, Limiter


def test_bucket_allows_up_to_capacity():
    bucket = Bucket(capacity=2, refill_seconds=60, tokens=2.0)
    assert bucket.take() is True
    assert bucket.take() is True
    assert bucket.take() is False


def test_bucket_refills_over_time():
    bucket = Bucket(capacity=2, refill_seconds=1.0, tokens=0.0)
    assert bucket.take(now=10.0) is False
    # two seconds of refill at one token per second is enough for one call
    assert bucket.take(now=12.0) is True


def test_bucket_never_exceeds_capacity():
    bucket = Bucket(capacity=3, refill_seconds=1.0, tokens=0.0)
    bucket.take(now=1000.0)
    assert bucket.tokens <= 3.0


def test_per_client_limit_blocks_one_client_only():
    limiter = Limiter(per_client=1, per_client_seconds=60, global_cap=10, global_seconds=60)
    assert limiter.allow("a").allowed is True
    assert limiter.allow("a").allowed is False
    assert limiter.allow("b").allowed is True


def test_global_limit_blocks_everyone():
    limiter = Limiter(per_client=10, per_client_seconds=60, global_cap=2, global_seconds=86400)
    assert limiter.allow("a").allowed is True
    assert limiter.allow("b").allowed is True
    decision = limiter.allow("c")
    assert decision.allowed is False
    assert decision.reason == "global limit"


def test_global_limit_zero_means_unlimited():
    limiter = Limiter(per_client=1, per_client_seconds=60, global_cap=0, global_seconds=60)
    assert limiter.allow("a").allowed is True
    assert limiter.allow("a").allowed is False  # per-client still applies


def test_per_client_zero_means_no_client_limit():
    limiter = Limiter(per_client=0, per_client_seconds=60, global_cap=5, global_seconds=60)
    assert all(limiter.allow("a").allowed for _ in range(5))


def test_blocked_decision_carries_retry_hint():
    limiter = Limiter(per_client=1, per_client_seconds=42, global_cap=0, global_seconds=0)
    limiter.allow("a")
    decision = limiter.allow("a")
    assert decision.allowed is False
    assert decision.retry_after == 42
