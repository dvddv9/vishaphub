"""The public doors: a ceiling on what a stranger can spend, and a run worth coming back to.

Speech is synthesised by an outside service and a run spends a model call, so both are
budgeted per address and the voice is cached by its words. Every finished run gets a
fingerprint and a page, so «the verdict was X» can be opened again instead of believed.
"""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from hub import fingerprint, limits, local, proposal, server
from hub.store import RunStore

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
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def post(self, path, body):
        data = json.dumps(body).encode()
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def get(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def get_with_headers(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=30) as response:
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
            status, _h, body = self.post("/run", {"spec": "name: demo\n", "api_key": "k",
                                                  "files": GOOD})
        payload = json.loads(body)
        assert status == 200
        run_id = payload["fingerprint"]["id"]
        assert run_id

        status, page = self.get(f"/r/{run_id}")
        assert status == 200
        text = page.decode()
        assert "PASS" in text and run_id in text
        assert "Not checked" in text

        status, raw = self.get(f"/api/runs/{run_id}.json")
        assert status == 200
        assert json.loads(raw)["result"]["verdict"] == "PASS"

        runs = json.loads(self.get("/api/runs")[1])
        assert any(r["id"] == run_id for r in runs["runs"])

        status, listing = self.get("/runs")
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
        status, headers, _ = self.get_with_headers("/")
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
        status, _h, body = self.post("/run", {"spec": "name: demo\n"})
        payload = json.loads(body)
        assert status == 502
        run_id = payload["fingerprint"]["id"]
        status, raw = self.get(f"/api/runs/{run_id}.json")
        assert status == 200
        kept = json.loads(raw)
        assert kept["result"]["verdict"] == "ERROR"
        assert "no model key" in kept["result"]["error"]

    def test_an_unknown_run_is_a_404(self):
        assert self.get("/r/deadbeefdeadbeef")[0] == 404
        assert self.get("/api/runs/deadbeefdeadbeef.json")[0] == 404


# the fingerprint --------------------------------------------------------------

class FingerprintTests(unittest.TestCase):
    def test_the_same_run_has_the_same_digest(self):
        args = dict(material="x = 1", spec="name: demo\n", files=GOOD,
                    plan={"stages": ["analyser"], "iterations": 1}, verdict="SAFE",
                    steps=[{"stage": "analyser", "verdict": "SAFE", "ok": True}])
        first = fingerprint.of(**args)
        second = fingerprint.of(**args)
        assert first["digest"] == second["digest"]
        assert first["id"] == first["digest"][:16]

    def test_a_different_verdict_is_a_different_run(self):
        base = dict(material="x = 1", spec="", files={}, plan={"stages": []}, steps=[])
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
