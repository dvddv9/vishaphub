"""Runs, and who read them, kept in Postgres per team.

Every operation is one transaction that first says which team it acts for (`app.current_team`, which the
row-level-security policies read) and then does its work AND writes the audit row, so a read that is not
in the audit trail did not happen. The queries also filter on team_id themselves: the policy is the net
under the code, not a replacement for it, and the tests check each separately.

What a run holds: the verdict, steps, findings, summary, the patch the model proposed and the fingerprint;
not the submitted code as such. See the README ("What happens to the data").
"""
from __future__ import annotations

import json

from . import db
from .access import Principal, key_hash

DEFAULT_RETENTION_DAYS = 30


def _jsonb(value):
    from psycopg.types.json import Jsonb
    return Jsonb(value)


class TeamStore:
    def __init__(self, url: str, default_retention_days: int = DEFAULT_RETENTION_DAYS):
        self.url = url
        self.default_retention_days = max(1, default_retention_days)

    # ---- plumbing -------------------------------------------------------------------------

    def _tx(self, team_id: str):
        """A connection inside one transaction that acts for `team_id` (commit on success, rollback on error)."""
        import contextlib

        @contextlib.contextmanager
        def manager():
            with db.connect(self.url) as conn:
                conn.execute("SELECT set_config('app.current_team', %s, true)", (team_id,))
                yield conn
        return manager()

    @staticmethod
    def _audit(conn, p: Principal, action: str, target: str | None = None, ip: str = "", detail: dict | None = None):
        conn.execute(
            "INSERT INTO audit_log (team_id, user_id, key_id, action, target, ip, detail) "
            "VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s)",
            (p.team_id, p.user_id, p.key_id, action, target, ip or None, _jsonb(detail or {})))

    # ---- who is asking --------------------------------------------------------------------

    def authenticate(self, token: str) -> Principal | None:
        with db.connect(self.url) as conn:
            row = conn.execute(
                "SELECT key_id, user_id, team_id, role, user_name, retention_days FROM hub_authenticate(%s)",
                (key_hash(token),)).fetchone()
        if row is None:
            return None
        return Principal(team_id=str(row[2]), user_id=str(row[1]), key_id=str(row[0]), role=row[3],
                         user_name=row[4], retention_days=row[5])

    # ---- runs -----------------------------------------------------------------------------

    def retention_days(self, p: Principal) -> int:
        return p.retention_days or self.default_retention_days

    def retention_note(self, p: Principal) -> str:
        """The line the report page shows, and the README quotes."""
        return (f"Kept in your team's database for {self.retention_days(p)} days from the run; an owner, or the "
                "person who made it, can delete it earlier.")

    def save(self, p: Principal, record: dict, ip: str = "") -> str:
        run_id = str(record["id"])
        with self._tx(p.team_id) as conn:
            conn.execute(
                "INSERT INTO runs (team_id, run_id, creators, expires_at, verdict, ok, plan, summary, result, cost) "
                "VALUES (%s::uuid, %s, ARRAY[%s::uuid], now() + make_interval(days => %s), %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (team_id, run_id) DO UPDATE SET created_at = now(), expires_at = EXCLUDED.expires_at, "
                "verdict = EXCLUDED.verdict, ok = EXCLUDED.ok, plan = EXCLUDED.plan, summary = EXCLUDED.summary, "
                "result = EXCLUDED.result, cost = EXCLUDED.cost, "
                "creators = (SELECT ARRAY(SELECT DISTINCT unnest(runs.creators || EXCLUDED.creators)))",
                (p.team_id, run_id, p.user_id, self.retention_days(p), record.get("verdict"), record.get("ok"),
                 _jsonb(record.get("plan")), record.get("summary", ""), _jsonb(record.get("result") or {}),
                 _jsonb(record.get("cost"))))
            self._audit(conn, p, "run.create", run_id, ip, {"verdict": record.get("verdict")})
        return run_id

    def get(self, p: Principal, run_id: str, ip: str = "") -> dict | None:
        with self._tx(p.team_id) as conn:
            row = conn.execute(
                "SELECT run_id, created_at, verdict, ok, plan, summary, result, cost FROM runs "
                "WHERE team_id = %s::uuid AND run_id = %s AND expires_at > now()", (p.team_id, run_id)).fetchone()
            self._audit(conn, p, "run.read", run_id, ip, {"found": row is not None})
        if row is None:
            return None
        return {"id": row[0], "at": row[1].isoformat(), "verdict": row[2], "ok": row[3], "plan": row[4],
                "summary": row[5] or "", "result": row[6], "cost": row[7]}

    def list(self, p: Principal, limit: int = 20, ip: str = "") -> list[dict]:
        with self._tx(p.team_id) as conn:
            rows = conn.execute(
                "SELECT run_id, created_at, verdict, ok, plan, summary FROM runs "
                "WHERE team_id = %s::uuid AND expires_at > now() ORDER BY created_at DESC LIMIT %s",
                (p.team_id, max(1, min(limit, 200)))).fetchall()
            self._audit(conn, p, "run.list", None, ip, {"count": len(rows)})
        return [{"id": r[0], "at": r[1].isoformat(), "verdict": r[2], "ok": r[3], "plan": r[4],
                 "summary": (r[5] or "")[:200]} for r in rows]

    def delete(self, p: Principal, run_id: str, ip: str = "") -> str:
        """'deleted', 'missing' or 'forbidden'. The run row goes, with the result and patch in it; the audit
        row stays (who, when, which id - no content)."""
        with self._tx(p.team_id) as conn:
            row = conn.execute(
                "SELECT creators FROM runs WHERE team_id = %s::uuid AND run_id = %s AND expires_at > now()",
                (p.team_id, run_id)).fetchone()
            if row is None:
                self._audit(conn, p, "run.delete", run_id, ip, {"outcome": "missing"})
                return "missing"
            mine = p.user_id in {str(u) for u in row[0]}
            if not (p.can("run.delete.any") or (p.can("run.delete.own") and mine)):
                self._audit(conn, p, "run.delete", run_id, ip, {"outcome": "forbidden"})
                return "forbidden"
            conn.execute("DELETE FROM runs WHERE team_id = %s::uuid AND run_id = %s", (p.team_id, run_id))
            self._audit(conn, p, "run.delete", run_id, ip, {"outcome": "deleted"})
        return "deleted"

    # ---- audit and retention ----------------------------------------------------------------

    def audit_events(self, p: Principal, limit: int = 100, before: int | None = None) -> list[dict]:
        with self._tx(p.team_id) as conn:
            rows = conn.execute(
                "SELECT id, at, user_id, key_id, action, target, ip, detail FROM audit_log "
                "WHERE team_id = %s::uuid AND (%s::bigint IS NULL OR id < %s::bigint) ORDER BY id DESC LIMIT %s",
                (p.team_id, before, before, max(1, min(limit, 500)))).fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), "user_id": str(r[2]) if r[2] else None,
                 "key_id": str(r[3]) if r[3] else None, "action": r[4], "target": r[5], "ip": r[6],
                 "detail": r[7]} for r in rows]

    def purge_expired(self) -> int:
        with db.connect(self.url) as conn:
            return conn.execute("SELECT hub_purge_expired()").fetchone()[0]


def to_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
