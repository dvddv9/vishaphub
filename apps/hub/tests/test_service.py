"""The public doors: a ceiling on what a stranger can spend, and a run worth coming back to.

Speech is synthesised by an outside service and a run spends a model call, so both are
budgeted per address and the voice is cached by its words. Every finished run gets a
fingerprint and a page, so «the verdict was X» can be opened again instead of believed.
"""
import json
import os
import secrets
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from hub import demo, fingerprint, limits, local, proposal, server
from hub.store import RunStore, owner_key

GOOD = {
    "calc/__init__.py": "def add(a, b):\n    return a + b\n",
    "test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
}
SPEC = {"entry": "calc", "files": ["calc/__init__.py", "test_calc.py"],
        "exports": ["add"], "tests": ["test_calc.py"]}
AUDIO = b"ID3fake-mp3-bytes"


def fake(**over):
    payload = {"ok": True, "model": "test-model", "verdict": "SAFE", "findings": [],
               "patch": {}, "questions": [], "proof": [], "summary": "looks fine"}
    payload.update(over)
    return payload


class ServerCase(unittest.TestCase):
    def setUp(self):
        # The budget is a subject of its own; a suite that makes more than six runs would
        # otherwise spend the window and test the 429 instead of the thing it names.
        self._saved_limits = dict(server.LIMITERS)
        for kind in server.LIMITERS:
            server.LIMITERS[kind] = limits.RateLimiter(0)
        self.addCleanup(lambda: server.LIMITERS.update(self._saved_limits))
        # the process-wide budget is a subject of its own as well; a suite must not spend it
        budget = mock.patch.object(server, "BUDGET", limits.RunBudget(0, 0))
        budget.start()
        self.addCleanup(budget.stop)
        chat_budget = mock.patch.object(server, "CHAT_BUDGET", limits.RunBudget(0, 0))
        chat_budget.start()
        self.addCleanup(chat_budget.stop)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    @staticmethod
    def cookie_of(headers) -> str:
        """`vishap_owner=<token>` from a response's Set-Cookie, or an empty string."""
        raw = {k.lower(): v for k, v in headers.items()}.get("set-cookie", "")
        return raw.split(";", 1)[0]

    @staticmethod
    def _who(cookie, headers):
        merged = dict(headers or {})
        if cookie:
            merged["Cookie"] = cookie
        return merged

    def post(self, path, body, cookie=None, headers=None):
        data = json.dumps(body).encode()
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                         headers={"Content-Type": "application/json",
                                                  **self._who(cookie, headers)}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def get(self, path, cookie=None, headers=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                         headers=self._who(cookie, headers))
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def get_with_headers(self, path, cookie=None, headers=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                         headers=self._who(cookie, headers))
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()


# limits -----------------------------------------------------------------------

class LimiterTests(unittest.TestCase):
    def test_a_window_counts_and_forgets(self):
        now = [0.0]
        lim = limits.RateLimiter(2, 60.0, clock=lambda: now[0])
        assert lim.allow("a") == (True, 0.0)
        assert lim.allow("a") == (True, 0.0)
        allowed, wait = lim.allow("a")
        assert allowed is False and wait > 0
        assert lim.allow("b")[0] is True
        now[0] = 61.0
        assert lim.allow("a")[0] is True

    def test_zero_turns_it_off(self):
        lim = limits.RateLimiter(0)
        assert all(lim.allow("a")[0] for _ in range(50))

    def test_the_voice_is_cached_by_its_words(self):
        cache = limits.TTSCache(items=2)
        key = limits.TTSCache.key("hello", "voice")
        assert cache.get(key) is None
        cache.put(key, AUDIO)
        assert cache.get(key) == AUDIO
        assert limits.TTSCache.key("hello", "other") != key

    def test_the_cache_is_bounded(self):
        cache = limits.TTSCache(items=2)
        for word in ("one", "two", "three"):
            cache.put(limits.TTSCache.key(word, "v"), AUDIO)
        assert cache.get(limits.TTSCache.key("one", "v")) is None
        assert cache.get(limits.TTSCache.key("three", "v")) == AUDIO


# the voice --------------------------------------------------------------------

class SpeakTests(ServerCase):
    def test_the_voice_is_synthesised_once(self):
        calls = {"n": 0}

        def speak(text):
            calls["n"] += 1
            return AUDIO

        with mock.patch.object(server, "tts_available", lambda: True), \
                mock.patch.object(server, "tts_speak", speak):
            first = self.post("/speak", {"text": "cached greeting"})
            second = self.post("/speak", {"text": "cached greeting"})

        assert first[0] == 200 and second[0] == 200
        assert calls["n"] == 1
        assert second[1].get("x-tts-cache") == "hit"

    def test_a_long_text_is_refused(self):
        ceiling = limits.tts_max_chars()
        status, _headers, out = self.post("/speak", {"text": "x" * (ceiling + 1)})
        assert status == 413
        assert "longer than" in json.loads(out)["error"]

    def test_the_voice_has_a_budget(self):
        saved = server.LIMITERS["speak"]
        server.LIMITERS["speak"] = limits.RateLimiter(1)
        try:
            with mock.patch.object(server, "tts_available", lambda: True), \
                    mock.patch.object(server, "tts_speak", lambda text: AUDIO):
                assert self.post("/speak", {"text": "one"})[0] == 200
                status, headers, out = self.post("/speak", {"text": "two"})
            assert status == 429
            assert "retry-after" in {k.lower() for k in headers}
            assert "too many" in json.loads(out)["error"]
        finally:
            server.LIMITERS["speak"] = saved


# runs -------------------------------------------------------------------------

class RunReportTests(ServerCase):
    def test_a_finished_run_gets_a_page_and_an_id(self):
        with mock.patch.object(proposal, "propose", lambda **kw: fake(summary="checked")), \
                mock.patch.object(local, "validate_code", lambda files, spec: {
                    "ok": True, "report": {"verdict": "PASS", "finding_count": 0, "checks": []}}):
            status, headers, body = self.post("/run", {"spec": "name: demo\n", "api_key": "k",
                                                       "files": GOOD})
        payload = json.loads(body)
        assert status == 200
        run_id = payload["fingerprint"]["id"]
        assert run_id
        cookie = self.cookie_of(headers)
        assert cookie.startswith("vishap_owner=")

        status, page = self.get(f"/r/{run_id}", cookie)
        assert status == 200
        text = page.decode()
        assert "PASS" in text and run_id in text
        assert "Not checked" in text

        status, raw = self.get(f"/api/runs/{run_id}.json", cookie)
        assert status == 200
        assert json.loads(raw)["result"]["verdict"] == "PASS"

        runs = json.loads(self.get("/api/runs", cookie)[1])
        assert any(r["id"] == run_id for r in runs["runs"])

        status, listing = self.get("/runs", cookie)
        assert status == 200
        assert run_id in listing.decode()


class PagesTests(ServerCase):
    def test_the_page_is_one_document_with_external_assets(self):
        status, body = self.get("/")
        assert status == 200
        text = body.decode()
        assert '<link rel="stylesheet" href="/styles.css">' in text
        assert '<script src="/app.js" defer></script>' in text
        assert "<style>" not in text and "<script>" not in text

    def test_the_stylesheet_and_the_script_are_served_and_cacheable(self):
        for path, kind in (("/styles.css", "text/css"), ("/app.js", "javascript"),
                           ("/favicon.svg", "image/svg+xml")):
            status, headers, body = self.get_with_headers(path)
            assert status == 200, path
            assert kind in headers.get("content-type", ""), path
            assert "max-age" in headers.get("cache-control", ""), path
            assert body

    def test_the_csp_no_longer_allows_inline_code(self):
        _status, headers, _ = self.get_with_headers("/")
        csp = headers.get("content-security-policy", "")
        assert "script-src 'self'" in csp
        assert "style-src 'self'" in csp
        assert "unsafe-inline" not in csp

    def test_an_unknown_run_is_a_page_not_json(self):
        status, body = self.get("/r/deadbeefdeadbeef")
        assert status == 404
        text = body.decode()
        assert "<!doctype html>" in text
        assert "No such run" in text

    def test_the_api_is_json_only(self):
        status, body = self.get("/api/nope")
        assert status == 404
        assert json.loads(body)["error"] == "not found"

    def test_a_refused_run_is_kept_with_its_reason(self):
        import os
        os.environ.pop("VISHAP_HUB_LLM_KEY", None)
        status, headers, body = self.post("/run", {"spec": "name: demo\n"})
        payload = json.loads(body)
        assert status == 502
        run_id = payload["fingerprint"]["id"]
        status, raw = self.get(f"/api/runs/{run_id}.json", self.cookie_of(headers))
        assert status == 200
        kept = json.loads(raw)
        assert kept["result"]["verdict"] == "ERROR"
        assert "no model key" in kept["result"]["error"]

    def test_an_unknown_run_is_a_404(self):
        assert self.get("/r/deadbeefdeadbeef")[0] == 404
        assert self.get("/api/runs/deadbeefdeadbeef.json")[0] == 404


# ownership --------------------------------------------------------------------

class _Done:
    """What run_plan returns, with nothing in it that depends on a model or on the analyser."""

    def as_dict(self):
        return {"ok": True, "verdict": "SAFE", "plan": {"stages": ["analyser"], "iterations": 1},
                "steps": [], "summary": "looks fine"}


class OwnershipTests(ServerCase):
    """A run is its maker's. The id is not a credential, and the list is not a window."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(server, "RUNS", RunStore(keep=50))
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_as(self, material, cookie=None, headers=None, **extra):
        body = {"material": material, "api_key": "k", **extra}
        with mock.patch.object(server, "run_plan", lambda **kw: _Done()):
            status, response_headers, raw = self.post("/run", body, cookie=cookie, headers=headers)
        assert status == 200, raw
        return json.loads(raw)["fingerprint"]["id"], response_headers

    # who gets a token

    def test_the_first_run_hands_out_a_token_and_a_later_one_does_not(self):
        _id, headers = self.run_as("a = 1")
        cookie = self.cookie_of(headers)
        assert cookie.startswith("vishap_owner=") and len(cookie.split("=", 1)[1]) >= 24
        _id, again = self.run_as("a = 2", cookie=cookie)
        assert self.cookie_of(again) == ""

    def test_the_cookie_is_not_readable_by_scripts_and_is_secure_behind_https(self):
        _id, headers = self.run_as("a = 1")
        flags = {k.lower(): v for k, v in headers.items()}["set-cookie"]
        assert "HttpOnly" in flags and "SameSite=Lax" in flags and "Secure" not in flags
        _id, behind = self.run_as("a = 3", headers={"x-forwarded-proto": "https"})
        assert "Secure" in {k.lower(): v for k, v in behind.items()}["set-cookie"]

    def test_the_token_is_stored_as_a_hash_and_never_returned(self):
        run_id, headers = self.run_as("secret = 1")
        cookie = self.cookie_of(headers)
        token = cookie.split("=", 1)[1]
        stored = server.RUNS.get(run_id)
        assert stored["owners"] == [owner_key(token)]
        assert token not in json.dumps(stored)
        _status, raw = self.get(f"/api/runs/{run_id}.json", cookie)
        assert "owners" not in json.loads(raw)

    def test_a_streamed_run_hands_out_a_token_too(self):
        with mock.patch.object(server, "run_plan", lambda **kw: _Done()):
            status, headers, body = self.post("/run/stream", {"material": "s = 1", "api_key": "k"})
        assert status == 200
        cookie = self.cookie_of(headers)
        assert cookie.startswith("vishap_owner=")
        done = body.decode().split("event: done\ndata: ", 1)[1].split("\n", 1)[0]
        run_id = json.loads(done)["fingerprint"]["id"]
        assert self.get(f"/api/runs/{run_id}.json", cookie)[0] == 200
        assert self.get(f"/api/runs/{run_id}.json")[0] == 404

    # the list

    def test_the_list_without_an_owner_is_forbidden_not_empty(self):
        self.run_as("a = 1")
        status, raw = self.get("/api/runs")
        assert status == 403
        assert "error" in json.loads(raw)
        status, page = self.get("/runs")
        assert status == 403
        assert "<!doctype html>" in page.decode()

    def test_a_malformed_token_is_no_token(self):
        assert self.get("/api/runs", headers={"x-vishap-owner": "short"})[0] == 403
        assert self.get("/api/runs", cookie="vishap_owner=short")[0] == 403

    def test_each_owner_lists_only_their_own_runs(self):
        a_id, a_headers = self.run_as("a = 1")
        b_id, b_headers = self.run_as("b = 2")
        a_list = json.loads(self.get("/api/runs", self.cookie_of(a_headers))[1])["runs"]
        b_list = json.loads(self.get("/api/runs", self.cookie_of(b_headers))[1])["runs"]
        assert [r["id"] for r in a_list] == [a_id]
        assert [r["id"] for r in b_list] == [b_id]
        _status, page = self.get("/runs", self.cookie_of(a_headers))
        assert a_id in page.decode() and b_id not in page.decode()

    # a run by id

    def test_a_stranger_gets_a_404_not_the_run(self):
        run_id, _h = self.run_as("a = 1")
        status, page = self.get(f"/r/{run_id}")
        assert status == 404
        assert run_id not in page.decode()
        status, raw = self.get(f"/api/runs/{run_id}.json")
        assert status == 404
        assert "result" not in json.loads(raw)

    def test_another_owner_gets_a_404_on_a_run_that_is_not_theirs(self):
        a_id, a_headers = self.run_as("a = 1")
        _b_id, b_headers = self.run_as("b = 2")
        a, b = self.cookie_of(a_headers), self.cookie_of(b_headers)
        assert self.get(f"/r/{a_id}", b)[0] == 404
        assert self.get(f"/api/runs/{a_id}.json", b)[0] == 404
        # and the answer is the one a run that never existed gets
        assert self.get("/r/0000000000000000", b)[1] == self.get(f"/r/{a_id}", b)[1]
        assert self.get(f"/r/{a_id}", a)[0] == 200
        assert self.get(f"/api/runs/{a_id}.json", a)[0] == 200

    def test_the_header_is_an_owner_like_the_cookie(self):
        token = secrets.token_urlsafe(24)
        run_id, headers = self.run_as("h = 1", headers={"x-vishap-owner": token})
        assert self.cookie_of(headers) == ""
        assert self.get(f"/api/runs/{run_id}.json", headers={"x-vishap-owner": token})[0] == 200
        assert self.get(f"/r/{run_id}", headers={"x-vishap-owner": token})[0] == 200
        assert self.get(f"/r/{run_id}", headers={"x-vishap-owner": secrets.token_urlsafe(24)})[0] == 404

    def test_two_visitors_with_the_same_code_both_keep_their_run(self):
        a_id, a_headers = self.run_as("same = 1")
        b_id, b_headers = self.run_as("same = 1")
        assert a_id == b_id
        a, b = self.cookie_of(a_headers), self.cookie_of(b_headers)
        assert self.get(f"/r/{a_id}", a)[0] == 200 and self.get(f"/r/{a_id}", b)[0] == 200
        assert self.get(f"/r/{a_id}")[0] == 404

    def test_private_answers_are_not_cacheable(self):
        run_id, headers = self.run_as("a = 1")
        cookie = self.cookie_of(headers)
        for path, who in (("/api/runs", cookie), (f"/r/{run_id}", cookie), (f"/r/{run_id}", None), ("/runs", None)):
            _s, response_headers, _b = self.get_with_headers(path, who)
            assert response_headers.get("cache-control") == "private, no-store", path

    # the one public run

    def test_the_pages_own_example_is_the_only_run_anyone_may_open(self):
        run_id, _h = self.run_as(demo.EXAMPLE_MATERIAL, question="is this safe?")
        assert self.get(f"/r/{run_id}")[0] == 200
        status, raw = self.get(f"/api/runs/{run_id}.json")
        assert status == 200 and "owners" not in json.loads(raw)
        assert self.get("/api/runs")[0] == 403      # public to open by id, not to list

    def test_a_flag_in_the_request_does_not_make_a_run_public(self):
        run_id, _h = self.run_as("private = 1", demo=True)
        assert self.get(f"/r/{run_id}")[0] == 404

    def test_the_example_with_anything_attached_is_not_a_demo(self):
        with_files, _h = self.run_as(demo.EXAMPLE_MATERIAL, files={"a.py": "x = 1"})
        assert self.get(f"/r/{with_files}")[0] == 404
        own_question, _h = self.run_as(demo.EXAMPLE_MATERIAL, question="what else is in my database?")
        assert self.get(f"/r/{own_question}")[0] == 404

    def test_the_demo_strings_are_the_ones_the_page_sends(self):
        with open(os.path.join(server.WEB, "app.js"), encoding="utf-8") as fh:
            script = fh.read()
        assert json.dumps(demo.EXAMPLE_MATERIAL) in script
        for question in demo.EXAMPLE_QUESTIONS - {""}:
            assert json.dumps(question, ensure_ascii=False) in script


class RetentionTests(ServerCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(server, "RUNS", RunStore(keep=7))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_report_page_says_how_long_the_run_lives(self):
        with mock.patch.object(server, "run_plan", lambda **kw: _Done()):
            _status, headers, raw = self.post("/run", {"material": "r = 1", "api_key": "k"})
        run_id = json.loads(raw)["fingerprint"]["id"]
        _status, page = self.get(f"/r/{run_id}", self.cookie_of(headers))
        assert server.RUNS.retention() in page.decode()
        assert "until the service restarts" in page.decode() and "last 7 runs" in page.decode()

    def test_with_the_file_mirror_it_says_so(self):
        import tempfile
        store = RunStore(keep=7, path=tempfile.mktemp(suffix=".json"))
        assert "in a file" in store.retention() and "restarts" not in store.retention()


class ReadmeTests(unittest.TestCase):
    def test_the_readme_quotes_the_line_the_report_page_shows(self):
        from pathlib import Path
        readme = (Path(__file__).resolve().parents[3] / "README.md").read_text(encoding="utf-8")
        assert RunStore(keep=200).retention() in readme

    def test_the_readme_quotes_the_line_a_teams_report_page_shows(self):
        from pathlib import Path

        from hub.access import Principal
        from hub.teamstore import TeamStore
        readme = (Path(__file__).resolve().parents[3] / "README.md").read_text(encoding="utf-8")
        person = Principal(team_id="t", user_id="u", key_id="k", role="member", user_name="n")
        assert TeamStore("postgresql://unused", 30).retention_note(person) in readme

    def test_the_readme_says_for_which_languages_safe_is_issued_and_it_is_true(self):
        import re
        from pathlib import Path

        from src.tools import safe_gate
        readme = (Path(__file__).resolve().parents[3] / "README.md").read_text(encoding="utf-8")
        said = re.search(r"SAFE is currently issued for: ([^.\n]+)\.", readme)
        assert said, "the README must say for which languages SAFE is issued"
        table = safe_gate.load_quality()["languages"]
        allowed = sorted(lang for lang, q in table.items() if q.get("safe_allowed") or (q.get("model_mode") or {}).get("safe_allowed"))
        assert said.group(1).strip() == (", ".join(allowed) if allowed else "no language")

    def test_the_readme_names_every_env_var_the_budget_reads(self):
        from pathlib import Path
        readme = (Path(__file__).resolve().parents[3] / "README.md").read_text(encoding="utf-8")
        for name in ("VISHAP_HUB_RUNS_KEEP", "VISHAP_HUB_RUNS_FILE", "VISHAP_HUB_GLOBAL_RUNS_PER_DAY",
                     "VISHAP_HUB_GLOBAL_CHARS_PER_DAY", "VISHAP_HUB_DATABASE_URL", "VISHAP_HUB_ADMIN_DATABASE_URL",
                     "VISHAP_HUB_REQUIRE_KEY", "VISHAP_HUB_RETENTION_DAYS", "VISHAP_HUB_PURGE_MINUTES",
                     "VISHAP_HUB_ALERT_WEBHOOK", "VISHAP_HUB_QUOTA_RUN_PER_USER", "VISHAP_HUB_QUOTA_RUN_PER_TEAM",
                     "VISHAP_HUB_TEAMS_GLOBAL_RUN_PER_DAY", "VISHAP_HUB_TEAMS_GLOBAL_CHARS_PER_DAY",
                     "VISHAP_HUB_TRUST_HEADER", "VISHAP_HUB_TRUSTED_HOPS"):
            assert name in readme, name


class VersionTests(unittest.TestCase):
    def test_pyproject_and_the_code_report_the_same_version(self):
        import tomllib
        from pathlib import Path

        from hub.version import __version__
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        assert tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"] == __version__


class ReviewRoutingTests(ServerCase):
    """Material with a question is a review when there is a model key to ask with; without one the rules still
    answer and the run says the question was not put to a model."""

    def sent_to_run_plan(self, body, key_in_env=False):
        seen = {}

        def capture(**kw):
            seen.update(kw)
            return _Done()

        env = {"VISHAP_HUB_LLM_KEY": "k"} if key_in_env else {}
        with mock.patch.dict(os.environ, env), mock.patch.object(server, "run_plan", capture):
            if not key_in_env:
                os.environ.pop("VISHAP_HUB_LLM_KEY", None)
            status = self.post("/run", body)[0]
        assert status == 200
        return seen

    def stages(self, seen):
        return [s.value for s in seen["plan"].stages]

    def test_material_and_a_question_with_the_callers_key_is_a_review(self):
        seen = self.sent_to_run_plan({"material": "a = 1", "question": "is this safe?", "api_key": "sk-ant-x"})
        assert self.stages(seen) == ["generator", "analyser"]
        assert seen["question"] == "is this safe?" and seen["plan"].model_optional

    def test_a_key_the_operator_set_counts_the_same(self):
        seen = self.sent_to_run_plan({"material": "a = 1", "question": "is this safe?"}, key_in_env=True)
        assert self.stages(seen) == ["generator", "analyser"]

    def test_without_any_key_the_rules_answer_and_the_note_says_the_question_went_unasked(self):
        seen = self.sent_to_run_plan({"material": "a = 1", "question": "is this safe?"})
        assert self.stages(seen) == ["analyser"]
        assert "question was not put to a model" in seen["plan"].note

    def test_a_saved_key_alone_does_not_turn_the_model_on(self):
        seen = self.sent_to_run_plan({"material": "a = 1", "api_key": "sk-ant-x"})    # no question: nothing to ask
        assert self.stages(seen) == ["analyser"] and "not put to a model" not in seen["plan"].note

    def test_an_explicit_intent_wins_and_is_not_second_guessed(self):
        seen = self.sent_to_run_plan({"material": "a = 1", "question": "is this safe?", "api_key": "k", "intent": "analyse"})
        assert self.stages(seen) == ["analyser"] and "not put to a model" not in seen["plan"].note

    def test_an_explicit_review_without_a_question_gets_a_default_one(self):
        seen = self.sent_to_run_plan({"material": "a = 1", "intent": "review", "api_key": "k"})
        assert self.stages(seen) == ["generator", "analyser"]
        assert "security" in seen["question"].lower()

    def test_a_spec_still_means_generation_and_a_bare_question_still_means_ask(self):
        assert self.stages(self.sent_to_run_plan({"spec": "x", "material": "a = 1", "api_key": "k"})) == ["generator", "validator", "analyser"]
        assert self.stages(self.sent_to_run_plan({"question": "what is this?", "api_key": "k"})) == ["generator"]


class ClientAddressTests(ServerCase):
    """Behind a proxy every visitor arrives from the proxy. The address the limits use must be the visitor's, and
    must not be something the visitor can choose."""

    def run_from(self, forwarded=None, header="x-forwarded-for"):
        headers = {header: forwarded} if forwarded else None
        with mock.patch.object(server, "run_plan", lambda **kw: _Done()):
            return self.post("/run", {"material": "a = 1", "api_key": "k"}, headers=headers)[0]

    def limit_to_one(self):
        patcher = mock.patch.dict(server.LIMITERS, {"run": limits.RateLimiter(1)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_without_a_trusted_header_a_spoofed_one_changes_nothing(self):
        self.limit_to_one()
        assert self.run_from("1.1.1.1") == 200
        assert self.run_from("2.2.2.2") == 429            # the same socket: the header was ignored

    def test_with_a_trusted_header_each_visitor_has_their_own_limit(self):
        self.limit_to_one()
        with mock.patch.object(server, "TRUST_HEADER", "x-forwarded-for"), mock.patch.object(server, "TRUSTED_HOPS", 1):
            assert self.run_from("9.9.9.9") == 200
            assert self.run_from("9.9.9.9") == 429
            assert self.run_from("8.8.8.8") == 200         # another visitor behind the same proxy

    def test_what_the_client_wrote_on_the_left_is_never_trusted(self):
        self.limit_to_one()
        with mock.patch.object(server, "TRUST_HEADER", "x-forwarded-for"), mock.patch.object(server, "TRUSTED_HOPS", 1):
            assert self.run_from("6.6.6.6, 9.9.9.9") == 200       # the proxy appended 9.9.9.9
            assert self.run_from("7.7.7.7, 9.9.9.9") == 429       # a new left side does not make a new visitor

    def test_two_proxies_in_front_means_the_second_from_the_right(self):
        self.limit_to_one()
        with mock.patch.object(server, "TRUST_HEADER", "x-forwarded-for"), mock.patch.object(server, "TRUSTED_HOPS", 2):
            assert self.run_from("5.5.5.5, 9.9.9.9, 10.0.0.1") == 200
            assert self.run_from("4.4.4.4, 9.9.9.9, 10.0.0.2") == 429

    def test_a_single_value_header_is_taken_as_it_is(self):
        self.limit_to_one()
        with mock.patch.object(server, "TRUST_HEADER", "true-client-ip"):
            assert self.run_from("3.3.3.3", "true-client-ip") == 200
            assert self.run_from("3.3.3.3", "true-client-ip") == 429
            assert self.run_from("3.3.3.4", "true-client-ip") == 200

    def test_a_value_that_is_not_an_address_is_not_a_key(self):
        self.limit_to_one()
        with mock.patch.object(server, "TRUST_HEADER", "x-forwarded-for"):
            assert self.run_from("not-an-address") == 200
            assert self.run_from("<script>") == 429            # both fall back to the socket address, which is one visitor


class StoreOwnershipTests(unittest.TestCase):
    def test_get_for_and_list_for_are_the_only_filtered_doors(self):
        store = RunStore(keep=5)
        store.save({"id": "mine", "verdict": "SAFE", "ok": True, "at": "1", "owners": ["a"]})
        store.save({"id": "theirs", "verdict": "SAFE", "ok": True, "at": "2", "owners": ["b"]})
        store.save({"id": "public", "verdict": "SAFE", "ok": True, "at": "3", "owners": ["b"], "demo": True})
        assert store.get_for("mine", "a")["id"] == "mine"
        assert store.get_for("theirs", "a") is None
        assert store.get_for("theirs", None) is None
        assert store.get_for("public", None)["id"] == "public"
        assert [r["id"] for r in store.list_for("a")] == ["mine"]
        assert store.list_for(None) == []

    def test_owners_merge_and_a_demo_flag_is_not_inherited(self):
        store = RunStore(keep=5)
        store.save({"id": "x", "owners": ["a"], "demo": True})
        store.save({"id": "x", "owners": ["b"], "demo": False})
        assert store.get("x")["owners"] == ["a", "b"]
        assert store.get_for("x", None) is None


# the ceiling for the whole process --------------------------------------------

class BudgetUnitTests(unittest.TestCase):
    def test_runs_in_a_window_are_counted_and_then_forgotten(self):
        now = [0.0]
        budget = limits.RunBudget(2, 0, window=100.0, clock=lambda: now[0])
        assert budget.take(10).allowed and budget.take(10).allowed
        third = budget.take(10)
        assert not third.allowed and third.wait > 0 and "2 runs" in third.reason
        now[0] = 101.0
        assert budget.take(10).allowed

    def test_characters_are_a_ceiling_of_their_own(self):
        budget = limits.RunBudget(0, 100, clock=lambda: 0.0)
        assert budget.take(60).allowed
        second = budget.take(60)
        assert not second.allowed and not second.too_big and "100 characters" in second.reason
        assert budget.used() == {"runs": 1, "chars": 60}

    def test_a_request_larger_than_the_whole_budget_is_called_what_it_is(self):
        verdict = limits.RunBudget(0, 100).take(101)
        assert not verdict.allowed and verdict.too_big

    def test_zero_turns_both_ceilings_off(self):
        budget = limits.RunBudget(0, 0)
        assert all(budget.take(10**9).allowed for _ in range(500))

    def test_the_default_is_conservative_and_the_environment_overrides_it(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VISHAP_HUB_GLOBAL_RUNS_PER_DAY", None)
            assert limits.global_runs_per_day() == 200
        with mock.patch.dict(os.environ, {"VISHAP_HUB_GLOBAL_RUNS_PER_DAY": "7"}):
            assert limits.global_runs_per_day() == 7

    def test_what_a_run_sends_in_is_counted(self):
        args = {"material": "abc", "question": "de", "spec": "f", "files": {"a.py": "gh", "b.py": "i"}}
        assert limits.input_chars(args) == 3 + 2 + 1 + 2 + 1
        assert limits.input_chars({"spec": {"entry": "x"}, "files": {}}) > 0


class BudgetServerTests(ServerCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(server, "RUNS", RunStore(keep=50))
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_once(self, path="/run", **body):
        body = {"material": "a = 1", "api_key": "k", **body}
        with mock.patch.object(server, "run_plan", lambda **kw: _Done()):
            return self.post(path, body)

    def test_the_run_after_the_last_one_is_a_429_with_a_reason_and_health_still_answers(self):
        with mock.patch.object(server, "BUDGET", limits.RunBudget(2, 0)):
            assert self.run_once()[0] == 200
            assert self.run_once()[0] == 200
            status, headers, raw = self.run_once()
            assert status == 429
            assert "budget of 2 runs" in json.loads(raw)["error"]
            assert int({k.lower(): v for k, v in headers.items()}["retry-after"]) >= 1
            assert self.run_once("/run/stream")[0] == 429
            assert self.get("/health")[0] == 200

    def test_a_request_too_large_for_the_budget_is_a_413(self):
        with mock.patch.object(server, "BUDGET", limits.RunBudget(0, 10)):
            assert self.run_once(material="x" * 11)[0] == 413

    def test_a_request_that_is_refused_for_its_form_spends_nothing(self):
        with mock.patch.object(server, "BUDGET", limits.RunBudget(1, 0)):
            assert self.run_once(intent="no-such-intent")[0] == 400
            assert self.run_once()[0] == 200

    def test_a_kept_run_shows_what_it_cost(self):
        status, headers, raw = self.run_once(material="a" * 40, question="is this safe?")
        assert status == 200
        run_id = json.loads(raw)["fingerprint"]["id"]
        _status, kept = self.get(f"/api/runs/{run_id}.json", self.cookie_of(headers))
        cost = json.loads(kept)["cost"]
        assert cost["input_chars"] == 40 + len("is this safe?")
        assert cost["result_chars"] > 0


# the fingerprint --------------------------------------------------------------

class FingerprintTests(unittest.TestCase):
    def test_the_same_run_has_the_same_digest(self):
        args = {"material": "x = 1", "spec": "name: demo\n", "files": GOOD,
                "plan": {"stages": ["analyser"], "iterations": 1}, "verdict": "SAFE",
                "steps": [{"stage": "analyser", "verdict": "SAFE", "ok": True}]}
        first = fingerprint.of(**args)
        second = fingerprint.of(**args)
        assert first["digest"] == second["digest"]
        assert first["id"] == first["digest"][:16]

    def test_a_different_verdict_is_a_different_run(self):
        base = {"material": "x = 1", "spec": "", "files": {}, "plan": {"stages": []}, "steps": []}
        assert fingerprint.of(verdict="SAFE", **base)["digest"] != \
            fingerprint.of(verdict="FAIL", **base)["digest"]

    def test_the_rules_are_named(self):
        rules = fingerprint.rules_version()
        assert set(rules) == {"hub", "validator", "analyser"}
        assert all(isinstance(v, str) and v for v in rules.values())


# the store --------------------------------------------------------------------

class StoreTests(unittest.TestCase):
    def test_it_keeps_the_newest_and_reports_a_list(self):
        store = RunStore(keep=2)
        for n in range(3):
            store.save({"id": f"run{n}", "verdict": "SAFE", "ok": True, "at": str(n)})
        assert store.get("run0") is None
        assert store.get("run2") is not None
        assert [r["id"] for r in store.list(10)] == ["run2", "run1"]

    def test_it_survives_a_restart_through_a_file(self):
        import tempfile
        path = tempfile.mktemp(suffix=".json")
        first = RunStore(keep=5, path=path)
        first.save({"id": "kept", "verdict": "PASS", "ok": True, "at": "now"})
        second = RunStore(keep=5, path=path)
        assert second.get("kept")["verdict"] == "PASS"


# streaming --------------------------------------------------------------------

class StreamTests(ServerCase):
    def test_the_run_is_announced_stage_by_stage(self):
        with mock.patch.object(proposal, "propose", lambda **kw: fake()), \
                mock.patch.object(local, "validate_code", lambda files, spec: {
                    "ok": True, "report": {"verdict": "PASS", "finding_count": 0, "checks": []}}):
            status, headers, body = self.post("/run/stream", {"spec": "name: demo\n",
                                                              "api_key": "k", "files": GOOD})
        assert status == 200
        assert headers.get("content-type", "").startswith("text/event-stream")
        text = body.decode()
        assert "event: stage" in text
        assert "event: done" in text
        stages = [line for line in text.splitlines() if line.startswith("data: ") and '"stage"' in line]
        assert any('"generator"' in line for line in stages)
        assert any('"validator"' in line for line in stages)

    def test_anonymous_chat_spends_the_global_budget(self):
        """A keyless page answered locally is free; a chat that reaches a model is a run."""
        model_reply = {"ok": True, "model": "test-model", "text": "pong"}
        with mock.patch.object(server, "CHAT_BUDGET", limits.RunBudget(1, 0)), \
             mock.patch.object(server, "reply", lambda *a, **k: model_reply), \
             mock.patch.dict(os.environ, {"VISHAP_HUB_LLM_KEY": "test-key"}):
            first, _, _ = self.post("/chat", {"message": "ping"})
            second, headers, body = self.post("/chat", {"message": "ping"})

        self.assertEqual(first, 200)
        self.assertEqual(second, 429)
        self.assertIn("budget", json.loads(body)["error"])
        self.assertIn("retry-after", {k.lower() for k in headers})

    def test_keyless_chat_does_not_spend_the_budget(self):
        """Without a key the answer is local, so it costs nothing and must not use the ceiling."""
        local_reply = {"ok": True, "model": "local", "text": "bring a key", "key_required": True}
        with mock.patch.object(server, "CHAT_BUDGET", limits.RunBudget(1, 0)), \
             mock.patch.object(server, "reply", lambda *a, **k: local_reply), \
             mock.patch.dict(os.environ, {"VISHAP_HUB_LLM_KEY": ""}):
            first, _, _ = self.post("/chat", {"message": "ping"})
            second, _, _ = self.post("/chat", {"message": "ping"})

        self.assertEqual([first, second], [200, 200])

    def test_chat_does_not_spend_the_run_budget(self):
        """A stranger talking on the site must not close the door for runs."""
        run_budget = limits.RunBudget(10, 0)
        model_reply = {"ok": True, "model": "test-model", "text": "pong"}
        with mock.patch.object(server, "BUDGET", run_budget), \
             mock.patch.object(server, "CHAT_BUDGET", limits.RunBudget(5, 0)), \
             mock.patch.object(server, "reply", lambda *a, **k: model_reply), \
             mock.patch.dict(os.environ, {"VISHAP_HUB_LLM_KEY": "test-key"}):
            for _ in range(3):
                status, _, _ = self.post("/chat", {"message": "ping"})
                self.assertEqual(status, 200)

        self.assertEqual(run_budget.used()["runs"], 0)
