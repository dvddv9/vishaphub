"""Who decides how submitted code is run: the person who installs the hub.

The hub runs the deliverable's own tests. That is executing someone else's code, and how much protection
it deserves depends on whose code it is, which only the installer knows:

* ``docker`` - only in a worker container (VISHAP_HUB_WORKER_IMAGE). No image, nothing is run.
* ``auto``   - the default and the behaviour before this setting existed: a worker container when one is
               configured, otherwise a network namespace where the platform has one, otherwise nothing is run
               when strict isolation is demanded.
* ``host``   - on this machine, as the same user, with the network guard that needs no privilege. For code
               the installer wrote or trusts. It is not a sandbox, and every result says so.

An unknown value is an error, not a silent fallback: a typo must not weaken or strengthen the policy.
"""
from __future__ import annotations

import os

MODES = ("docker", "auto", "host")
ENV = "VISHAP_HUB_ISOLATION"


class PolicyError(ValueError):
    pass


def policy() -> str:
    raw = (os.getenv(ENV) or "auto").strip().lower()
    if raw not in MODES:
        raise PolicyError(f"{ENV}={raw!r} is not one of {', '.join(MODES)}")
    return raw


def host_record(network: str) -> dict:
    """What a run on the host puts into its result, so nobody reads it as a sandboxed run."""
    return {"kind": "host", "policy": "host", "network": network, "confirmed": False,
            "note": "ran on the host as the hub's user; the network guard is not a sandbox"}
