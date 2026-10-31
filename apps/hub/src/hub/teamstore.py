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
from dataclasses import dataclass

from . import db, limits
from . import meter as meter_mod
from .access import Principal, key_hash

DEFAULT_RETENTION_DAYS = 30
WINDOW_HOURS = 24

#: Placeholders, not derived from anyone's costs: (per person, per team) requests in a sliding 24 hours.
#: They exist so that no door is unlimited by default; set the real numbers in the environment
#: (VISHAP_HUB_QUOTA_RUN_PER_USER ...) or per team (hub.admin set-quota). 0 means no limit.
DEFAULT_QUOTAS = {"run": (50, 200), "chat": (100, 500), "speak": (100, 500)}
#: The same for the whole hub's team traffic, summed over every team (VISHAP_HUB_TEAMS_GLOBAL_RUN_PER_DAY ...).
DEFAULT_GLOBAL_REQUESTS = {"run": 500, "chat": 1000, "speak": 1000}
DEFAULT_GLOBAL_RUN_CHARS = 20_000_000


@dataclass(frozen=True)
class Reserved:
    usage_id: int
    #: (scope, used after this request, limit, label) for every limit that applies: the alerter reads these
    counts: tuple


@dataclass(frozen=True)
class Denied:
    scope: str                  # "user", "team" or "global"
    used: int
    limit: int
    retry_after: int            # seconds until the oldest request in the window leaves it
    message: str


def quota_for(p: Principal, kind: str) -> tuple[int, int]:
    """(per person, per team) for this kind: the team's own override, else the environment, else the placeholder."""
    own = (p.quotas or {}).get(kind) or {}
    env_user, env_team = DEFAULT_QUOTAS[kind]
    user = own.get("user", limits.int_env(f"VISHAP_HUB_QUOTA_{kind.upper()}_PER_USER", env_user))
    team = own.get("team", limits.int_env(f"VISHAP_HUB_QUOTA_{kind.upper()}_PER_TEAM", env_team))
    return int(user), int(team)


def global_limits(kind: str) -> tuple[int, int]:
    """(requests, run characters) a day over every team; 0 means no limit."""
    requests = limits.int_env(f"VISHAP_HUB_TEAMS_GLOBAL_{kind.upper()}_PER_DAY", DEFAULT_GLOBAL_REQUESTS[kind])
    chars = limits.int_env("VISHAP_HUB_TEAMS_GLOBAL_CHARS_PER_DAY", DEFAULT_GLOBAL_RUN_CHARS) if kind == "run" else 0
    return requests, chars


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
                "SELECT key_id, user_id, team_id, role, user_name, retention_days, quotas FROM hub_authenticate(%s)",
                (key_hash(token),)).fetchone()
        if row is None:
            return None
        return Principal(team_id=str(row[2]), user_id=str(row[1]), key_id=str(row[0]), role=row[3],
                         user_name=row[4], retention_days=row[5], quotas=row[6] or {})

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
                "SELECT run_id, created_at, verdict, ok, plan, summary, "
                "result #>> '{statuses,fix,status}', result #>> '{statuses,verification,status}' FROM runs "
                "WHERE team_id = %s::uuid AND expires_at > now() ORDER BY created_at DESC LIMIT %s",
                (p.team_id, max(1, min(limit, 200)))).fetchall()
            self._audit(conn, p, "run.list", None, ip, {"count": len(rows)})
        return [{"id": r[0], "at": r[1].isoformat(), "verdict": r[2], "ok": r[3], "plan": r[4],
                 "summary": (r[5] or "")[:200], "fix": r[6], "verification": r[7]} for r in rows]

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
            # the usage rows keep their numbers and let go of the id: it pointed at content that is gone
            conn.execute("UPDATE usage SET run_id = NULL WHERE team_id = %s::uuid AND run_id = %s", (p.team_id, run_id))
            self._audit(conn, p, "run.delete", run_id, ip, {"outcome": "deleted"})
        return "deleted"

    # ---- quotas and usage ---------------------------------------------------------------------

    def reserve(self, p: Principal, kind: str, chars: int, ip: str = "") -> Reserved | Denied:
        """Take one request out of the person's, the team's and the hub's allowance, or say which one is spent.

        One lock serialises every reservation, so eight requests arriving together against a limit of three
        let exactly three through. A refused request is not counted (it spent nothing) but is audited.
        """
        user_limit, team_limit = quota_for(p, kind)
        global_requests, global_chars = global_limits(kind)
        window = "now() - make_interval(hours => %s)"
        with self._tx(p.team_id) as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('hub:usage', 0))")
            retry = "greatest(1, ceil(extract(epoch FROM (min(at) + make_interval(hours => %s) - now()))))::integer"
            user_used, user_retry = conn.execute(
                f"SELECT count(*), {retry} FROM usage WHERE team_id = %s::uuid AND user_id = %s::uuid AND kind = %s "
                f"AND at > {window}", (WINDOW_HOURS, p.team_id, p.user_id, kind, WINDOW_HOURS)).fetchone()
            team_used, team_retry = conn.execute(
                f"SELECT count(*), {retry} FROM usage WHERE team_id = %s::uuid AND kind = %s AND at > {window}",
                (WINDOW_HOURS, p.team_id, kind, WINDOW_HOURS)).fetchone()
            g_used, g_chars_used, g_retry = conn.execute("SELECT requests, chars, retry_after FROM hub_global_usage(%s, %s)",
                                                         (kind, WINDOW_HOURS)).fetchone()
            denied = None
            for scope, used, limit, retry_after, what in (
                    ("user", user_used, user_limit, user_retry, "your own"),
                    ("team", team_used, team_limit, team_retry, "your team's"),
                    ("global", g_used, global_requests, g_retry, "the hub's")):
                if limit > 0 and used >= limit:
                    denied = Denied(scope, used, limit, int(retry_after or 3600),
                                    f"{what} daily limit of {limit} {kind} requests is used up")
                    break
            if denied is None and global_chars > 0 and g_chars_used + chars > global_chars:
                denied = Denied("global", g_chars_used, global_chars, int(g_retry or 3600),
                                f"the hub's daily budget of {global_chars} characters for runs is used up")
            if denied is not None:
                self._audit(conn, p, "quota.denied", kind, ip, {"scope": denied.scope, "used": denied.used,
                                                                "limit": denied.limit})
                return denied
            usage_id = conn.execute(
                "INSERT INTO usage (team_id, user_id, kind, input_chars) VALUES (%s::uuid, %s::uuid, %s, %s) RETURNING id",
                (p.team_id, p.user_id, kind, max(0, chars))).fetchone()[0]
        counts = (
            (f"quota:user:{p.user_id}:{kind}", user_used + 1, user_limit, f"{p.user_name}'s {kind} requests"),
            (f"quota:team:{p.team_id}:{kind}", team_used + 1, team_limit, f"team {p.team_id} {kind} requests"),
            (f"global:{kind}", g_used + 1, global_requests, f"all teams' {kind} requests"),
        )
        return Reserved(usage_id, counts)

    def finish(self, p: Principal, usage_id: int, run_id: str | None, input_chars: int, result_chars: int,
               meter: meter_mod.Meter | None, outcome: str) -> None:
        """Fill in what the request turned out to cost. Provider tokens and the estimate go to separate columns."""
        measured = meter.measured() if meter else None
        est = meter_mod.estimate(input_chars, result_chars)
        with self._tx(p.team_id) as conn:
            conn.execute(
                "UPDATE usage SET run_id = %s, result_chars = %s, tokens_in = %s, tokens_out = %s, model_calls = %s, "
                "measured_calls = %s, est_tokens_in = %s, est_tokens_out = %s, outcome = %s "
                "WHERE id = %s AND team_id = %s::uuid",
                (run_id, result_chars, measured["input"] if measured else None, measured["output"] if measured else None,
                 meter.calls if meter else 0, meter.measured_calls if meter else 0, est["input"], est["output"],
                 outcome, usage_id, p.team_id))

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
