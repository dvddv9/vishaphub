"""Operator commands for team mode. They connect as the database owner, never as the server's role.

    export VISHAP_HUB_ADMIN_DATABASE_URL=postgresql://owner:...@host/db
    python -m hub.admin migrate --app-password '...'     # schema, and a login for the server's role
    python -m hub.admin create-team acme --retention-days 30
    python -m hub.admin create-user acme alice owner      # roles: owner, member, viewer
    python -m hub.admin issue-key <user-id>               # prints the key once; only its hash is kept
    python -m hub.admin revoke-key <key-id>
    python -m hub.admin disable-user <user-id>
    python -m hub.admin list
    python -m hub.admin purge-expired                     # the server also does this on a timer
    python -m hub.admin audit acme --limit 50
    python -m hub.admin purge-team acme --yes [--include-audit]

There is no self-service yet: a team is created by an operator, and so is every person and every key.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

from . import db
from .access import ROLES, key_hash, new_key

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _team_id(conn, team: str) -> str:
    row = conn.execute("SELECT id FROM teams WHERE " + ("id = %s::uuid" if _UUID.match(team) else "name = %s"),
                       (team,)).fetchone()
    if row is None:
        raise SystemExit(f"no such team: {team}")
    return str(row[0])


def create_team(url: str, name: str, retention_days: int | None = None) -> str:
    with db.connect(url) as conn:
        return str(conn.execute("INSERT INTO teams (name, retention_days) VALUES (%s, %s) RETURNING id",
                                (name, retention_days)).fetchone()[0])


def create_user(url: str, team: str, name: str, role: str) -> str:
    if role not in ROLES:
        raise SystemExit(f"role must be one of {', '.join(ROLES)}")
    with db.connect(url) as conn:
        team_id = _team_id(conn, team)
        return str(conn.execute("INSERT INTO users (team_id, name, role) VALUES (%s::uuid, %s, %s) RETURNING id",
                                (team_id, name, role)).fetchone()[0])


def issue_key(url: str, user_id: str) -> tuple[str, str]:
    """(key id, the key). The key is returned once and is not recoverable: only its hash is stored."""
    token = new_key()
    with db.connect(url) as conn:
        row = conn.execute("INSERT INTO api_keys (user_id, prefix, key_hash) VALUES (%s::uuid, %s, %s) RETURNING id",
                           (user_id, token[:12], key_hash(token))).fetchone()
    return str(row[0]), token


def revoke_key(url: str, key_id: str) -> bool:
    with db.connect(url) as conn:
        return conn.execute("UPDATE api_keys SET revoked_at = now() WHERE id = %s::uuid AND revoked_at IS NULL",
                            (key_id,)).rowcount == 1


def disable_user(url: str, user_id: str) -> bool:
    with db.connect(url) as conn:
        return conn.execute("UPDATE users SET disabled_at = now() WHERE id = %s::uuid AND disabled_at IS NULL",
                            (user_id,)).rowcount == 1


def list_all(url: str) -> list[dict]:
    with db.connect(url) as conn:
        rows = conn.execute(
            "SELECT t.name, t.id, t.retention_days, u.name, u.id, u.role, u.disabled_at IS NOT NULL, "
            "k.id, k.prefix, k.revoked_at IS NOT NULL, k.last_used_at "
            "FROM teams t LEFT JOIN users u ON u.team_id = t.id LEFT JOIN api_keys k ON k.user_id = u.id "
            "ORDER BY t.name, u.name, k.created_at").fetchall()
    keys = ("team", "team_id", "retention_days", "user", "user_id", "role", "disabled", "key_id", "key_prefix",
            "revoked", "last_used_at")
    return [dict(zip(keys, (str(v) if hasattr(v, "hex") else v for v in r))) for r in rows]


def purge_expired(url: str) -> int:
    with db.connect(url) as conn:
        return conn.execute("SELECT hub_purge_expired()").fetchone()[0]


def audit(url: str, team: str, limit: int = 50) -> list[dict]:
    with db.connect(url) as conn:
        team_id = _team_id(conn, team)
        rows = conn.execute("SELECT id, at, user_id, action, target, ip, detail FROM audit_log "
                            "WHERE team_id = %s::uuid ORDER BY id DESC LIMIT %s", (team_id, limit)).fetchall()
    return [{"id": r[0], "at": r[1].isoformat(), "user_id": str(r[2]) if r[2] else None, "action": r[3],
             "target": r[4], "ip": r[5], "detail": r[6]} for r in rows]


def purge_team(url: str, team: str, include_audit: bool = False) -> dict:
    """Remove a team: its runs, people and keys. The audit trail stays unless `include_audit` says otherwise."""
    with db.connect(url) as conn:
        team_id = _team_id(conn, team)
        counts = {
            "runs": conn.execute("SELECT count(*) FROM runs WHERE team_id = %s::uuid", (team_id,)).fetchone()[0],
            "users": conn.execute("SELECT count(*) FROM users WHERE team_id = %s::uuid", (team_id,)).fetchone()[0],
            "keys": conn.execute("SELECT count(*) FROM api_keys k JOIN users u ON u.id = k.user_id "
                                 "WHERE u.team_id = %s::uuid", (team_id,)).fetchone()[0],
        }
        conn.execute("INSERT INTO audit_log (team_id, action, detail) VALUES (%s::uuid, 'team.purged', "
                     "%s::jsonb)", (team_id, '{"include_audit": %s}' % ("true" if include_audit else "false")))
        conn.execute("DELETE FROM teams WHERE id = %s::uuid", (team_id,))          # cascades users, keys, runs
        counts["audit_deleted"] = (conn.execute("DELETE FROM audit_log WHERE team_id = %s::uuid", (team_id,)).rowcount
                                   if include_audit else 0)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hub.admin", description=__doc__.split("\n")[0])
    parser.add_argument("--url", default=os.getenv("VISHAP_HUB_ADMIN_DATABASE_URL", ""),
                        help="owner connection URL (default: $VISHAP_HUB_ADMIN_DATABASE_URL)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("migrate"); m.add_argument("--app-password")
    c = sub.add_parser("create-team"); c.add_argument("name"); c.add_argument("--retention-days", type=int)
    u = sub.add_parser("create-user"); u.add_argument("team"); u.add_argument("name"); u.add_argument("role", choices=ROLES)
    k = sub.add_parser("issue-key"); k.add_argument("user_id")
    r = sub.add_parser("revoke-key"); r.add_argument("key_id")
    d = sub.add_parser("disable-user"); d.add_argument("user_id")
    sub.add_parser("list")
    sub.add_parser("purge-expired")
    a = sub.add_parser("audit"); a.add_argument("team"); a.add_argument("--limit", type=int, default=50)
    p = sub.add_parser("purge-team"); p.add_argument("team"); p.add_argument("--include-audit", action="store_true")
    p.add_argument("--yes", action="store_true", help="required: this deletes a team's runs, people and keys")
    args = parser.parse_args(argv)
    if not args.url:
        parser.error("set VISHAP_HUB_ADMIN_DATABASE_URL or pass --url")

    if args.cmd == "migrate":
        done = db.migrate(args.url, args.app_password)
        print("applied: " + (", ".join(done) if done else "nothing - already up to date"))
    elif args.cmd == "create-team":
        print(create_team(args.url, args.name, args.retention_days))
    elif args.cmd == "create-user":
        print(create_user(args.url, args.team, args.name, args.role))
    elif args.cmd == "issue-key":
        key_id, token = issue_key(args.url, args.user_id)
        print(f"key id: {key_id}\nkey:    {token}\nThis is the only time the key is shown.")
    elif args.cmd == "revoke-key":
        print("revoked" if revoke_key(args.url, args.key_id) else "no such active key")
    elif args.cmd == "disable-user":
        print("disabled" if disable_user(args.url, args.user_id) else "no such active user")
    elif args.cmd == "list":
        for row in list_all(args.url):
            print(row)
    elif args.cmd == "purge-expired":
        print(f"removed {purge_expired(args.url)} expired run(s)")
    elif args.cmd == "audit":
        for row in audit(args.url, args.team, args.limit):
            print(row)
    elif args.cmd == "purge-team":
        if not args.yes:
            parser.error("purge-team needs --yes")
        print(purge_team(args.url, args.team, args.include_audit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
