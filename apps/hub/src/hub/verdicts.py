"""One ranking for every verdict in the hub.

Two modules used to rank verdicts by hand — the pipeline and the single-pass run —
and the two tables disagreed: `one.py` put EMERGENCY level with FAIL, `pipeline.py`
put it above. A security signal that a failing test can hide is the wrong answer, so
the stricter reading wins and this module is the only place that decides.

The order is the product's own: SAFE and PASS are the same answer to different
questions, NEEDS_REVIEW and REQUIRES_REVIEW are the same doubt, FAIL is a broken
promise, EMERGENCY is danger, ERROR is a run that could not answer at all.
"""
from __future__ import annotations

#: Rank decides which verdict survives a merge. Higher is stricter.
#: EMERGENCY sits above FAIL: a security signal must not be hidden by a failing test.
SEVERITY_ORDER = {
    "SAFE": 0,
    "PASS": 0,
    "NEEDS_REVIEW": 1,
    "REQUIRES_REVIEW": 1,
    "FAIL": 3,
    "EMERGENCY": 4,
    "ERROR": 5,
}

#: A run that ends in one of these did not pass its own gates.
BLOCKING_VERDICTS = frozenset({"FAIL", "ERROR", "EMERGENCY"})


def normalise(verdict: object) -> str:
    """Upper-case a verdict and reject anything the ranking does not know."""
    text = str(verdict or "").strip().upper()
    if text not in SEVERITY_ORDER:
        raise ValueError(f"unknown verdict: {verdict!r}")
    return text


def rank(verdict: str) -> int:
    """Rank that never raises: an unreadable verdict is an ERROR, not a pass."""
    try:
        return SEVERITY_ORDER[normalise(verdict)]
    except ValueError:
        return SEVERITY_ORDER["ERROR"]


def strictest(*verdicts: str) -> str:
    """The strictest of the verdicts given; an empty answer is an ERROR."""
    known = [normalise(v) for v in verdicts if v]
    if not known:
        raise ValueError("no verdict to merge")
    return max(known, key=rank)


def is_blocking(verdict: str) -> bool:
    return normalise(verdict) in BLOCKING_VERDICTS
