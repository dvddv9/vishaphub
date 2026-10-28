"""Key checks without a web framework.

Each service used to carry its own copy of this logic, and the copies drifted:
the analyser accepted tenant keys and public demo, the generator did not. Here the
rule is one function with explicit flags, so a difference between services is a
difference in configuration, not in code.

Nothing here raises HTTP errors: the framework adapter turns a ``Decision`` into a
response, which keeps the rule testable without FastAPI.
"""
from __future__ import annotations

import hmac
from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    ALLOW = "allow"
    MISSING = "missing"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class KeyPolicy:
    """Everything that can change the answer, named."""

    expected_key: str = ""
    allow_no_key: bool = False      # trusted loopback / test environment
    public_demo: bool = False       # server pays, caller needs no key
    require_user_key: bool = False  # bring-your-own-key only


def check_key(provided: str, policy: KeyPolicy) -> Decision:
    """Decide whether a request may proceed.

    Order matters and is deliberate:

    1. a matching static key always passes — no database, no network;
    2. bring-your-own-key mode rejects an empty key before anything else, because
       there is nothing to fall back to;
    3. public demo allows a keyless call — the limit, not the key, bounds the spend;
    4. no key configured at all is only allowed when the deployment says so
       explicitly, never by accident.
    """
    provided = (provided or "").strip()
    expected = (policy.expected_key or "").strip()

    if provided and expected and hmac.compare_digest(provided, expected):
        return Decision.ALLOW

    if policy.require_user_key:
        return Decision.MISSING if not provided else Decision.ALLOW

    if policy.public_demo:
        return Decision.ALLOW

    if not expected:
        return Decision.ALLOW if policy.allow_no_key else Decision.UNAVAILABLE

    return Decision.MISSING if not provided else Decision.INVALID
