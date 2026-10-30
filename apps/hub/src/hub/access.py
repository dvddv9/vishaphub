"""Who is asking, and what that person may do.

Three roles. Everyone in a team can read the team's runs; what differs is what else they may do:

  owner   everything a member can, plus: delete any run of the team, read the audit trail
  member  run, read the team's runs, delete the runs they made themselves
  viewer  read the team's runs - nothing that spends or removes

A key belongs to one person (user) in one team. The key itself is shown once, when it is issued; the
database keeps only its SHA-256, which is enough for a 256-bit random value. Keys are sent as
`Authorization: Bearer vhk_...` or `x-vishap-key: vhk_...`.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass

KEY_PREFIX = "vhk_"
KEY_COOKIE = "vishap_key"
_KEY = re.compile(r"vhk_[A-Za-z0-9_-]{32,128}")

ROLES = ("owner", "member", "viewer")
PERMISSIONS = {
    "owner": frozenset({"run.create", "run.read", "run.delete.any", "run.delete.own", "audit.read"}),
    "member": frozenset({"run.create", "run.read", "run.delete.own"}),
    "viewer": frozenset({"run.read"}),
}


def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def key_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def allowed(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, frozenset())


@dataclass(frozen=True)
class Principal:
    """One authenticated key: the person, their team and their role."""
    team_id: str
    user_id: str
    key_id: str
    role: str
    user_name: str
    retention_days: int | None = None

    def can(self, permission: str) -> bool:
        return allowed(self.role, permission)


def credentials(headers) -> tuple[str, str] | None:
    """What the request presented: ("key", token), ("bad", "") for something that is not a key, or None.

    The header comes first, then x-vishap-key, then the cookie /login sets for browsers.
    """
    auth = (headers.get("authorization") or "").strip()
    candidate = ""
    if auth.lower().startswith("bearer "):
        candidate = auth[7:].strip()
    elif auth:
        return ("bad", "")
    if not candidate:
        candidate = (headers.get("x-vishap-key") or "").strip()
    if not candidate:
        for part in (headers.get("cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == KEY_COOKIE:
                candidate = value.strip()
                break
    if not candidate:
        return None
    return ("key", candidate) if _KEY.fullmatch(candidate) else ("bad", "")
