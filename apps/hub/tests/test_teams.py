"""Team mode on a real Postgres: who may read a run, who may delete it, how long it lives, who looked.

Needs TEST_POSTGRES_URL (a superuser). Each module run builds a scratch database, runs the migrations there
and connects as vishap_hub_app (NOSUPERUSER, NOBYPASSRLS), then drops it. Without the variable the tests
skip - the only way they skip; CI sets it and fails the build if any of them skipped.
"""
import contextlib
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock
from urllib.parse import urlsplit, urlunsplit

from test_service import ServerCase  # tests/ is on sys.path (rootdir import mode)

from hub import access, admin, db, limits, server
from hub.teamstore import TeamStore

RAW = os.getenv("TEST_POSTGRES_URL", "").replace("postgresql+asyncpg://", "postgresql://")
needs_pg = unittest.skipUnless(RAW, "TEST_POSTGRES_URL not set")
SCRATCH = "hub_teams_test"
APP_PASSWORD = "hub_app_test_only"
ADMIN_URL = APP_URL = ""


def _url(database=None, user=None, password=None) -> str:
    parts = urlsplit(RAW)
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    auth = f"{user}:{password}@" if user else f"{parts.username}:{parts.password}@"
    return urlunsplit((parts.scheme, auth + host, "/" + (database or parts.path.lstrip("/")), "", ""))


def setUpModule():
    global ADMIN_URL, APP_URL
    if not RAW:
        return
    import psycopg
    with psycopg.connect(_url("postgres"), autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {SCRATCH}")
    ADMIN_URL = _url(SCRATCH)
    db.migrate(ADMIN_URL, app_password=APP_PASSWORD)
    APP_URL = _url(SCRATCH, db.APP_ROLE, APP_PASSWORD)


def tearDownModule():
    if not RAW:
        return
    import psycopg
    with psycopg.connect(_url("postgres"), autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
        with contextlib.suppress(Exception):        # the role may be gone
            conn.execute(f"ALTER ROLE {db.APP_ROLE} NOLOGIN PASSWORD NULL")


class _Said:
    """A finished run that says one distinctive thing, so a test can look for it afterwards."""

    def __init__(self, text="looks fine"):
        self.text = text

    def as_dict(self):
        return {"ok": True, "verdict": "SAFE", "plan": {"stages": ["analyser"], "iterations": 1}, "steps": [],
                "summary": self.text, "findings": [{"rule": "x", "message": self.text}]}


@needs_pg
class TeamCase(ServerCase):
    """Two teams: alpha (alice owner, amy member, vic viewer) and beta (bob owner, bea member)."""

    def setUp(self):
        super().setUp()
        import psycopg
        with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
            conn.execute("TRUNCATE audit_log, runs, api_keys, users, teams CASCADE")
        self.store = TeamStore(APP_URL, 30)
        for patcher in (mock.patch.object(server, "TEAMS", self.store),
                        mock.patch.object(server, "REQUIRE_KEY", False)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.alpha = admin.create_team(ADMIN_URL, "alpha")
        self.beta = admin.create_team(ADMIN_URL, "beta")
        self.keys, self.users = {}, {}
        for team, name, role in (("alpha", "alice", "owner"), ("alpha", "amy", "member"), ("alpha", "vic", "viewer"),
                                 ("beta", "bob", "owner"), ("beta", "bea", "member")):
            self.users[name] = admin.create_user(ADMIN_URL, team, name, role)
            self.keys[name] = admin.issue_key(ADMIN_URL, self.users[name])[1]

    # ---- plumbing
    def call(self, method, path, key=None, body=None, headers=None, cookie=None):
        merged = dict(headers or {})
        if key:
            merged["Authorization"] = f"Bearer {key}"
        if cookie:
            merged["Cookie"] = cookie
        data = json.dumps(body).encode() if body is not None else None
        if data:
            merged["Content-Type"] = "application/json"
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=merged, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()

    def run_as(self, who, material="a = 1", said="looks fine"):
        with mock.patch.object(server, "run_plan", lambda **kw: _Said(said)):
            status, _h, raw = self.call("POST", "/run", self.keys[who], {"material": material, "api_key": "k"})
        assert status == 200, raw
        return json.loads(raw)["fingerprint"]["id"]

    def admin_rows(self, sql, *args):
        import psycopg
        with psycopg.connect(ADMIN_URL) as conn:
            return conn.execute(sql, args).fetchall()


@needs_pg
class IdentityTests(TeamCase):
    def test_a_key_is_one_person_in_one_team(self):
        p = self.store.authenticate(self.keys["amy"])
        assert (p.user_name, p.role, p.team_id) == ("amy", "member", self.alpha)
        assert self.store.authenticate("vhk_" + "x" * 43) is None

    def test_a_revoked_key_and_a_disabled_person_stop_working(self):
        key_id = self.admin_rows("SELECT k.id FROM api_keys k JOIN users u ON u.id = k.user_id WHERE u.name = 'bea'")[0][0]
        assert self.store.authenticate(self.keys["bea"]) is not None
        assert admin.revoke_key(ADMIN_URL, str(key_id))
        assert self.store.authenticate(self.keys["bea"]) is None
        assert self.store.authenticate(self.keys["amy"]) is not None
        assert admin.disable_user(ADMIN_URL, self.users["amy"])
        assert self.store.authenticate(self.keys["amy"]) is None

    def test_only_a_hash_of_the_key_is_stored(self):
        token = self.keys["alice"]
        text = json.dumps(self.admin_rows("SELECT * FROM api_keys"), default=str)
        assert token not in text and access.key_hash(token) in text

    def test_a_wrong_key_is_a_401_and_never_falls_back_to_anonymous(self):
        for path in ("/api/runs", "/api/me"):
            assert self.call("GET", path, "vhk_" + "y" * 43)[0] == 401
        status, _h, _b = self.call("POST", "/run", "vhk_" + "y" * 43, {"material": "a = 1"})
        assert status == 401
        assert self.call("GET", "/api/runs", headers={"Authorization": "Basic abc"})[0] == 401

    def test_who_am_i(self):
        status, _h, raw = self.call("GET", "/api/me", self.keys["vic"])
        me = json.loads(raw)
        assert status == 200 and me["role"] == "viewer" and me["retention_days"] == 30
        assert "run.create" not in me["permissions"] and "run.read" in me["permissions"]


@needs_pg
class RestartTests(TeamCase):
    def test_a_restart_keeps_the_runs(self):
        run_id = self.run_as("alice", "keep = 1")
        again = TeamStore(APP_URL, 30)                                   # a new process, the same database
        principal = again.authenticate(self.keys["alice"])
        assert again.get(principal, run_id)["verdict"] == "SAFE"
        with mock.patch.object(server, "TEAMS", again):
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                request = urllib.request.Request(f"http://127.0.0.1:{httpd.server_address[1]}/api/runs/{run_id}",
                                                 headers={"Authorization": f"Bearer {self.keys['alice']}"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    assert response.status == 200
                    assert json.loads(response.read())["id"] == run_id
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_the_run_keeps_who_made_it_and_what_it_cost(self):
        run_id = self.run_as("amy", "cost = 1")
        creators, cost = self.admin_rows("SELECT creators, cost FROM runs WHERE run_id = %s", run_id)[0]
        assert [str(c) for c in creators] == [self.users["amy"]]
        assert cost["input_chars"] == len("cost = 1")


@needs_pg
class IsolationTests(TeamCase):
    def test_another_team_cannot_read_a_run_by_id_page_or_list(self):
        run_id = self.run_as("alice", "secret = 1", said="ALPHA-ONLY-TEXT")
        for path in (f"/api/runs/{run_id}", f"/r/{run_id}", f"/api/runs/{run_id}.json"):
            status, _h, body = self.call("GET", path, self.keys["bob"])
            assert status == 404 and b"ALPHA-ONLY-TEXT" not in body, path
        listed = json.loads(self.call("GET", "/api/runs", self.keys["bob"])[2])["runs"]
        assert listed == []
        assert [r["id"] for r in json.loads(self.call("GET", "/api/runs", self.keys["alice"])[2])["runs"]] == [run_id]

    def test_another_team_cannot_delete_it_and_cannot_tell_it_exists(self):
        run_id = self.run_as("alice", "secret = 2")
        status, _h, _b = self.call("DELETE", f"/api/runs/{run_id}", self.keys["bob"])
        assert status == 404
        assert self.call("DELETE", "/api/runs/0000000000000000", self.keys["bob"])[0] == 404
        assert len(self.admin_rows("SELECT 1 FROM runs WHERE run_id = %s", run_id)) == 1

    def test_the_same_code_in_two_teams_is_two_runs(self):
        a, b = self.run_as("alice", "same = 1", "from alpha"), self.run_as("bob", "same = 1", "from beta")
        assert a == b
        assert json.loads(self.call("GET", f"/api/runs/{a}", self.keys["alice"])[2])["summary"] == "from alpha"
        assert json.loads(self.call("GET", f"/api/runs/{a}", self.keys["bob"])[2])["summary"] == "from beta"
        assert self.call("DELETE", f"/api/runs/{a}", self.keys["alice"])[0] == 200
        assert self.call("GET", f"/api/runs/{a}", self.keys["bob"])[0] == 200          # beta's copy is untouched

    def test_the_database_alone_keeps_the_teams_apart_without_a_where(self):
        run_id = self.run_as("alice", "rls = 1")
        import psycopg
        with psycopg.connect(APP_URL) as conn:
            conn.execute("SELECT set_config('app.current_team', %s, true)", (self.beta,))
            assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
            assert conn.execute("UPDATE runs SET summary = 'x'").rowcount == 0
            assert conn.execute("DELETE FROM runs").rowcount == 0
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute("INSERT INTO runs (team_id, run_id, creators, expires_at, result) VALUES "
                             "(%s::uuid, 'x', ARRAY[%s::uuid], now(), '{}')", (self.alpha, self.users["bob"]))
        with psycopg.connect(APP_URL) as conn:                          # no team named at all: nothing is visible
            assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
        with psycopg.connect(APP_URL) as conn:
            conn.execute("SELECT set_config('app.current_team', %s, true)", (self.alpha,))
            assert [r[0] for r in conn.execute("SELECT run_id FROM runs").fetchall()] == [run_id]   # and it is not "nothing works"

    def test_the_server_role_cannot_reach_identities_or_rewrite_the_audit_trail(self):
        import psycopg
        self.run_as("alice", "audit = 1")
        for sql in ("SELECT * FROM api_keys", "SELECT * FROM users", "SELECT * FROM teams",
                    "UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log", "TRUNCATE audit_log"):
            with psycopg.connect(APP_URL) as conn, self.assertRaises(psycopg.errors.InsufficientPrivilege, msg=sql):
                conn.execute("SELECT set_config('app.current_team', %s, true)", (self.alpha,))
                conn.execute(sql)


@needs_pg
class RoleTests(TeamCase):
    def test_a_viewer_reads_and_nothing_else(self):
        run_id = self.run_as("alice", "viewer = 1")
        assert self.call("GET", f"/api/runs/{run_id}", self.keys["vic"])[0] == 200
        for path in ("/run", "/chat", "/speak"):
            status, _h, _b = self.call("POST", path, self.keys["vic"], {"material": "a = 1", "message": "hi", "text": "hi"})
            assert status == 403, path
        assert self.call("DELETE", f"/api/runs/{run_id}", self.keys["vic"])[0] == 403
        assert len(self.admin_rows("SELECT 1 FROM runs")) == 1

    def test_a_member_deletes_their_own_run_not_someone_elses(self):
        owners_run, members_run = self.run_as("alice", "o = 1"), self.run_as("amy", "m = 1")
        assert self.call("DELETE", f"/api/runs/{owners_run}", self.keys["amy"])[0] == 403
        assert self.call("DELETE", f"/api/runs/{members_run}", self.keys["amy"])[0] == 200
        assert self.call("GET", f"/api/runs/{owners_run}", self.keys["amy"])[0] == 200       # members read the team's runs

    def test_an_owner_deletes_any_run_of_the_team(self):
        run_id = self.run_as("amy", "m = 2")
        assert self.call("DELETE", f"/api/runs/{run_id}", self.keys["alice"])[0] == 200

    def test_only_an_owner_reads_the_audit_trail(self):
        self.run_as("amy", "a = 1")
        assert self.call("GET", "/api/team/audit", self.keys["amy"])[0] == 403
        assert self.call("GET", "/api/team/audit", self.keys["vic"])[0] == 403
        assert self.call("GET", "/api/team/audit")[0] == 401
        assert self.call("GET", "/api/team/audit", self.keys["alice"])[0] == 200


@needs_pg
class DeletionTests(TeamCase):
    def test_delete_removes_the_run_and_what_is_in_it_and_keeps_only_a_content_free_audit_row(self):
        run_id = self.run_as("alice", "gone = 1", said="DISTINCTIVE-FINDING-TEXT")
        assert self.admin_rows("SELECT count(*) FROM runs WHERE result::text LIKE %s", "%DISTINCTIVE-FINDING-TEXT%")[0][0] == 1
        assert self.call("DELETE", f"/api/runs/{run_id}", self.keys["alice"])[0] == 200
        assert self.admin_rows("SELECT count(*) FROM runs")[0][0] == 0
        everywhere = json.dumps(self.admin_rows("SELECT * FROM audit_log"), default=str)
        assert "DISTINCTIVE-FINDING-TEXT" not in everywhere
        deleted = self.admin_rows("SELECT target, detail FROM audit_log WHERE action = 'run.delete'")
        assert deleted == [(run_id, {"outcome": "deleted"})]
        assert self.call("GET", f"/api/runs/{run_id}", self.keys["alice"])[0] == 404

    def test_deleting_a_team_clears_runs_people_and_keys_and_the_audit_only_when_asked(self):
        self.run_as("bob", "b = 1")
        counts = admin.purge_team(ADMIN_URL, "beta")
        assert counts == {"runs": 1, "users": 2, "keys": 2, "audit_deleted": 0}
        assert self.admin_rows("SELECT count(*) FROM runs WHERE team_id = %s", self.beta)[0][0] == 0
        assert self.admin_rows("SELECT count(*) FROM users WHERE team_id = %s", self.beta)[0][0] == 0
        assert self.store.authenticate(self.keys["bob"]) is None
        kept = {r[0] for r in self.admin_rows("SELECT action FROM audit_log WHERE team_id = %s", self.beta)}
        assert {"run.create", "team.purged"} <= kept
        admin.purge_team(ADMIN_URL, "alpha", include_audit=True)
        assert self.admin_rows("SELECT count(*) FROM audit_log WHERE team_id = %s", self.alpha)[0][0] == 0

    def test_purge_team_asks_for_confirmation(self):
        with self.assertRaises(SystemExit):
            admin.main(["--url", ADMIN_URL, "purge-team", "beta"])
        assert self.admin_rows("SELECT count(*) FROM teams")[0][0] == 2


@needs_pg
class RetentionTests(TeamCase):
    def test_the_default_is_thirty_days_and_a_team_can_have_its_own(self):
        run_id = self.run_as("alice", "r = 1")
        days = self.admin_rows("SELECT extract(epoch FROM expires_at - created_at) / 86400 FROM runs WHERE run_id = %s", run_id)[0][0]
        assert round(float(days)) == 30
        short = admin.create_team(ADMIN_URL, "short", retention_days=2)
        user = admin.create_user(ADMIN_URL, "short", "sam", "member")
        self.keys["sam"] = admin.issue_key(ADMIN_URL, user)[1]
        sam_run = self.run_as("sam", "r = 2")
        days = self.admin_rows("SELECT extract(epoch FROM expires_at - created_at) / 86400 FROM runs WHERE team_id = %s", short)[0][0]
        assert round(float(days)) == 2 and sam_run

    def test_an_expired_run_is_unreadable_at_once_and_purged_with_an_audit_row(self):
        run_id = self.run_as("alice", "old = 1")
        self.admin_rows("SELECT 1")
        import psycopg
        with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
            conn.execute("UPDATE runs SET expires_at = now() - interval '1 minute'")
        assert self.call("GET", f"/api/runs/{run_id}", self.keys["alice"])[0] == 404          # before any purge
        assert json.loads(self.call("GET", "/api/runs", self.keys["alice"])[2])["runs"] == []
        assert self.store.purge_expired() == 1
        assert self.admin_rows("SELECT count(*) FROM runs")[0][0] == 0
        assert self.admin_rows("SELECT detail FROM audit_log WHERE action = 'run.expired'") == [({"count": 1},)]
        assert self.store.purge_expired() == 0

    def test_a_run_again_refreshes_its_life(self):
        run_id = self.run_as("alice", "again = 1")
        import psycopg
        with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
            conn.execute("UPDATE runs SET expires_at = now() + interval '1 hour'")
        assert self.run_as("alice", "again = 1") == run_id
        days = self.admin_rows("SELECT extract(epoch FROM expires_at - now()) / 86400 FROM runs")[0][0]
        assert round(float(days)) == 30


@needs_pg
class AuditTests(TeamCase):
    def test_the_audit_trail_records_who_did_what_including_reads_and_refusals(self):
        run_id = self.run_as("amy", "watched = 1")
        self.call("GET", f"/api/runs/{run_id}", self.keys["alice"])
        self.call("GET", "/api/runs/0000000000000000", self.keys["alice"])
        self.call("GET", "/api/runs", self.keys["vic"])
        self.call("DELETE", f"/api/runs/{run_id}", self.keys["vic"])
        events = json.loads(self.call("GET", "/api/team/audit", self.keys["alice"])[2])["events"]
        seen = {(e["action"], e["target"], e["user_id"], json.dumps(e["detail"], sort_keys=True)) for e in events}
        assert ("run.create", run_id, self.users["amy"], '{"verdict": "SAFE"}') in seen
        assert ("run.read", run_id, self.users["alice"], '{"found": true}') in seen
        assert ("run.read", "0000000000000000", self.users["alice"], '{"found": false}') in seen
        assert ("run.list", None, self.users["vic"], '{"count": 1}') in seen
        assert ("run.delete", run_id, self.users["vic"], '{"outcome": "forbidden"}') in seen
        assert all(e["key_id"] for e in events if e["action"] != "run.expired")

    def test_one_team_never_sees_anothers_audit_trail(self):
        self.run_as("alice", "x = 1")
        events = json.loads(self.call("GET", "/api/team/audit", self.keys["bob"])[2])["events"]
        assert events == []

    def test_the_trail_pages_backwards(self):
        for n in range(5):
            self.run_as("alice", f"page = {n}")
        first = json.loads(self.call("GET", "/api/team/audit?limit=2", self.keys["alice"])[2])["events"]
        older = json.loads(self.call("GET", f"/api/team/audit?limit=2&before={first[-1]['id']}", self.keys["alice"])[2])["events"]
        assert len(first) == len(older) == 2 and older[0]["id"] < first[-1]["id"]
        assert self.call("GET", "/api/team/audit?limit=x", self.keys["alice"])[0] == 400


@needs_pg
class BrowserAccessTests(TeamCase):
    def test_signing_in_gives_a_browser_the_teams_pages(self):
        run_id = self.run_as("alice", "page = 1")
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/login", data=f"key={self.keys['alice']}".encode(),
                                         headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        try:
            urllib.request.build_opener(NoRedirect).open(request, timeout=30)
            raise AssertionError("expected a redirect")
        except urllib.error.HTTPError as exc:
            assert exc.code == 303 and exc.headers["Location"] == "/runs"
            cookie = exc.headers["Set-Cookie"]
        assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
        pair = cookie.split(";", 1)[0]
        status, _h, page = self.call("GET", f"/r/{run_id}", cookie=pair)
        assert status == 200 and b"Kept in your team" in page and b"30 days" in page
        assert run_id.encode() in self.call("GET", "/runs", cookie=pair)[2]

    def test_a_wrong_key_does_not_sign_in_and_a_bad_cookie_says_so(self):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/login", data=b"key=vhk_nope", method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=30)
        assert caught.exception.code == 401
        status, _h, page = self.call("GET", "/runs", cookie="vishap_key=vhk_" + "z" * 43)
        assert status == 401 and b"Sign in at /login" in page


@needs_pg
class RequireKeyTests(TeamCase):
    def test_with_the_setting_on_every_spending_door_needs_a_key(self):
        with mock.patch.object(server, "REQUIRE_KEY", True):
            for path in ("/run", "/chat", "/speak"):
                status, _h, _b = self.call("POST", path, None, {"material": "a = 1", "message": "hi", "text": "hi"})
                assert status == 401, path
            assert self.run_as("amy", "ok = 1")

    def test_anonymous_mode_still_works_when_the_setting_is_off(self):
        with mock.patch.object(server, "run_plan", lambda **kw: _Said()):
            status, headers, _b = self.call("POST", "/run", None, {"material": "anon = 1", "api_key": "k"})
        assert status == 200 and "set-cookie" in headers


@needs_pg
class StorageFailureTests(TeamCase):
    def test_a_database_that_is_down_is_a_503_not_a_silent_anonymous_run(self):
        broken = TeamStore("postgresql://nobody:x@127.0.0.1:1/none", 30)
        with mock.patch.object(server, "TEAMS", broken):
            assert self.call("GET", "/api/runs", self.keys["alice"])[0] == 503
            assert self.call("POST", "/run", self.keys["alice"], {"material": "a = 1"})[0] == 503

    def test_a_run_that_could_not_be_stored_says_so(self):
        with mock.patch.object(self.store, "save", side_effect=RuntimeError("disk full")), \
                mock.patch.object(server, "run_plan", lambda **kw: _Said()):
            status, _h, raw = self.call("POST", "/run", self.keys["alice"], {"material": "lost = 1", "api_key": "k"})
        assert status == 200 and json.loads(raw)["stored"] is False


@needs_pg
class AdminTests(unittest.TestCase):
    def test_the_operator_commands(self):
        assert admin.main(["--url", ADMIN_URL, "create-team", "cli-team", "--retention-days", "5"]) == 0
        user = admin.create_user(ADMIN_URL, "cli-team", "cat", "member")
        key_id, token = admin.issue_key(ADMIN_URL, user)
        assert token.startswith("vhk_") and len(token) > 40
        rows = [r for r in admin.list_all(ADMIN_URL) if r["team"] == "cli-team"]
        assert rows and rows[0]["retention_days"] == 5 and rows[0]["key_prefix"] == token[:12]
        assert all(token not in json.dumps(r) for r in rows)
        assert admin.main(["--url", ADMIN_URL, "revoke-key", key_id]) == 0
        assert not admin.revoke_key(ADMIN_URL, key_id)
        with self.assertRaises(SystemExit):
            admin.create_user(ADMIN_URL, "cli-team", "x", "emperor")
        with self.assertRaises(SystemExit):
            admin.create_user(ADMIN_URL, "no-such-team", "x", "member")
        admin.purge_team(ADMIN_URL, "cli-team", include_audit=True)

    def test_migrations_apply_once(self):
        assert db.migrate(ADMIN_URL) == []


class OfflineTests(unittest.TestCase):
    """These need no database."""

    def test_roles_and_permissions(self):
        assert access.allowed("owner", "audit.read") and not access.allowed("member", "audit.read")
        assert access.allowed("member", "run.create") and not access.allowed("viewer", "run.create")
        assert access.allowed("viewer", "run.read") and not access.allowed("viewer", "run.delete.own")
        assert not access.allowed("ghost", "run.read")

    def test_credentials_come_from_the_header_then_the_cookie(self):
        key = access.new_key()
        assert access.credentials({}) is None
        assert access.credentials({"authorization": f"Bearer {key}"}) == ("key", key)
        assert access.credentials({"x-vishap-key": key}) == ("key", key)
        assert access.credentials({"cookie": f"a=b; {access.KEY_COOKIE}={key}"}) == ("key", key)
        assert access.credentials({"authorization": "Bearer nope"}) == ("bad", "")
        assert access.credentials({"authorization": "Basic abc"}) == ("bad", "")

    def test_a_key_is_long_random_and_hashed(self):
        a, b = access.new_key(), access.new_key()
        assert a != b and a.startswith("vhk_") and len(a) >= 40
        assert access.key_hash(a) != a and len(access.key_hash(a)) == 64

    def test_without_the_variable_team_mode_is_off_and_loads_no_driver(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VISHAP_HUB_DATABASE_URL", None)
            assert server._init_teams() is None
        with mock.patch.dict(os.environ, {"VISHAP_HUB_DATABASE_URL": "postgresql://x@h/d", "VISHAP_HUB_RETENTION_DAYS": "7"}):
            store = server._init_teams()
            assert store.default_retention_days == 7 and limits.int_env("VISHAP_HUB_RETENTION_DAYS", 30) == 7


if __name__ == "__main__":
    unittest.main()
