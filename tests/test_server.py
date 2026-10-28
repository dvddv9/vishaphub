import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from tests.helpers import EXAMPLE
from tests.test_deliver import CLEAN_SPEC
from tests.test_pipeline import Stub, answer
from tests.test_verify import GOOD, TODAY

from generator import server
from generator.server import LOOPBACK, make_handler

SPEC_TEXT = CLEAN_SPEC.read_text(encoding="utf-8")


class ServerCase(unittest.TestCase):
    token = None

    @classmethod
    def setUpClass(cls):
        cls.stub = Stub(answer(GOOD))
        handler = make_handler(cls.token, set(LOOPBACK), run_kwargs={
            "chat_fn": cls.stub, "analyzer": None, "today": TODAY})
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def req(self, path, body=None, headers=None, method=None, raw=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"Content-Type": "application/json"} if data is not None else {}
        h.update(headers or {})
        r = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def post(self, path, body, **kw):
        status, data = self.req(path, body, **kw)
        return status, json.loads(data)


class ApiTests(ServerCase):
    def test_health_and_form(self):
        self.assertEqual(self.req("/health")[0], 200)
        status, data = self.req("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Vishap Generator", data)

    def test_unknown_path(self):
        self.assertEqual(self.req("/nope")[0], 404)
        self.assertEqual(self.req("/api/nope", {"spec": "x"})[0], 404)

    def test_check_does_not_call_the_model(self):
        before = len(self.stub.calls)
        status, out = self.post("/api/check", {"spec": SPEC_TEXT})
        self.assertEqual(status, 200)
        self.assertEqual(len(out["requirements"]), 6)
        self.assertEqual(len(self.stub.calls), before)
        self.assertNotIn("files", out)

    def test_generate_returns_files_and_never_writes(self):
        status, out = self.post("/api/generate", {"spec": SPEC_TEXT})
        self.assertEqual(status, 200, out.get("error"))
        self.assertEqual(out["verify"]["code_verdict"], "passed", out["verify"])
        self.assertIn("handlers/user.py", out["files"])
        self.assertTrue(out["deliver"]["dry_run"])
        self.assertIn("trace", out)
        self.assertTrue(any("[Deliver]" in line for line in out["log"]))

    def test_bad_spec_is_422(self):
        status, out = self.post("/api/generate", {"spec": "version: 1\n"})
        self.assertEqual(status, 422)
        self.assertTrue(out["error"].startswith("spec:"))

    def test_spec_field_is_validated(self):
        self.assertEqual(self.post("/api/generate", {})[0], 400)
        self.assertEqual(self.post("/api/generate", {"spec": 5})[0], 400)
        self.assertEqual(self.post("/api/generate", {"spec": SPEC_TEXT, "repairs": 99})[0], 400)
        self.assertEqual(self.post("/api/generate", {"spec": SPEC_TEXT, "repairs": True})[0], 400)
        self.assertEqual(self.post("/api/generate", {"spec": "x" * 100_001})[0], 413)

    def test_body_rules(self):
        self.assertEqual(self.req("/api/check", raw=b"not json")[0], 400)
        self.assertEqual(self.req("/api/check", raw=b"[1]")[0], 400)
        self.assertEqual(self.req("/api/check", raw=b"x" * (server.MAX_BODY + 1))[0], 413)
        self.assertEqual(self.req("/api/check", raw=b"{}", headers={"Content-Type": "text/plain"})[0], 415)

    def test_foreign_origin_and_host_are_refused(self):
        self.assertEqual(self.req("/api/check", {"spec": SPEC_TEXT},
                                  headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.req("/health", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.req("/api/check", {"spec": SPEC_TEXT},
                                  headers={"Origin": "http://localhost:8787"})[0], 200)

    def test_second_run_while_busy_gets_429(self):
        self.assertTrue(server._RUN_LOCK.acquire(blocking=False))
        try:
            status, out = self.post("/api/generate", {"spec": SPEC_TEXT})
        finally:
            server._RUN_LOCK.release()
        self.assertEqual(status, 429)

    def test_gate_example_spec_through_the_api(self):
        status, out = self.post("/api/generate", {"spec": EXAMPLE.read_text(encoding="utf-8"),
                                                  "gate": True, "repairs": 0})
        self.assertEqual(status, 200)
        self.assertTrue(out["deliver"]["blocked"])
        self.assertEqual(out["exit_code"], 1)


class UiSupportTests(ServerCase):
    def test_status(self):
        status, data = self.req("/api/status")
        out = json.loads(data)
        self.assertEqual(status, 200)
        self.assertEqual(out["version"], __import__("generator").__version__)
        self.assertIn(out["coverage"], ("package", "built-in"))
        self.assertTrue(out["client_llm_allowed"])
        self.assertFalse(out["token_required"])
        for key in ("llm_from_environment", "analyzer_found", "ruff_found"):
            self.assertIsInstance(out[key], bool)

    def test_examples(self):
        status, data = self.req("/api/examples")
        out = json.loads(data)["examples"]
        self.assertEqual(status, 200)
        self.assertEqual([e["id"] for e in out], ["user-lookup", "with-a-gap", "order-signed-in"])
        self.assertTrue(all("{today}" not in e["spec"] for e in out))

    def test_generate_returns_the_diff(self):
        status, out = self.post("/api/generate", {"spec": SPEC_TEXT})
        self.assertEqual(status, 200)
        self.assertIn("+++ b/handlers/user.py", out["diff"])

    def test_client_llm_is_validated_like_the_environment(self):
        for llm, word in (({"url": "", "model": "m"}, "CUSTOM_LLM_URL"),
                          ({"url": "https://x.example", "model": ""}, "CUSTOM_LLM_MODEL"),
                          ({"url": "https://x.example", "model": "m", "key": ""}, "CUSTOM_LLM_KEY"),
                          ({"url": "http://x.example", "model": "m", "key": "k"}, "https"),
                          ({"url": "https://x.example", "model": "m", "key": "k", "thinking": "maybe"}, "THINKING")):
            with self.subTest(llm=llm):
                status, out = self.post("/api/generate", {"spec": SPEC_TEXT, "llm": llm})
                self.assertEqual(status, 400)
                self.assertTrue(out["error"].startswith("llm:"), out)
                self.assertIn(word, out["error"])
        self.assertEqual(self.post("/api/generate", {"spec": SPEC_TEXT, "llm": "x"})[0], 400)
        self.assertEqual(self.post("/api/generate", {"spec": SPEC_TEXT, "llm": {"url": 5}})[0], 400)

    def test_the_key_is_never_echoed(self):
        llm = {"url": "https://x.example", "model": "m", "key": "sk-very-secret-1234", "thinking": ""}
        status, data = self.req("/api/check", {"spec": SPEC_TEXT, "llm": llm})
        self.assertNotIn(b"sk-very-secret-1234", data)

    def test_a_valid_client_llm_reaches_the_pipeline(self):
        seen = {}

        def fake_run(path, **kw):
            seen.update(kw)
            from generator.pipeline import PipelineResult
            return PipelineResult(exit_code=0)

        out = server.handle_generate(
            {"spec": SPEC_TEXT, "llm": {"url": "https://x.example", "model": "m", "key": "k"}},
            check_only=False, run=fake_run)
        self.assertEqual(seen["config"].model, "m")
        self.assertEqual(seen["config"].key, "k")
        self.assertNotIn("llm", out)

    def test_client_llm_can_be_refused(self):
        with self.assertRaises(server.ApiError) as cm:
            server.handle_generate({"spec": SPEC_TEXT, "llm": {"url": "https://x.example", "model": "m", "key": "k"}},
                                   check_only=False, client_llm=False)
        self.assertEqual(cm.exception.status, 403)


class TokenTests(ServerCase):
    token = "s3cret-token"

    def test_post_needs_the_token(self):
        self.assertEqual(self.req("/api/check", {"spec": SPEC_TEXT})[0], 401)
        self.assertEqual(self.req("/api/check", {"spec": SPEC_TEXT},
                                  headers={"Authorization": "Bearer wrong"})[0], 401)
        self.assertEqual(self.req("/api/check", {"spec": SPEC_TEXT},
                                  headers={"Authorization": "Bearer s3cret-token"})[0], 200)

    def test_the_form_page_is_open(self):
        self.assertEqual(self.req("/")[0], 200)


class ServeTests(unittest.TestCase):
    def test_non_loopback_host_needs_a_token(self):
        import os
        os.environ.pop("GENERATOR_API_TOKEN", None)
        self.assertEqual(server.serve("0.0.0.0", 0), 2)


if __name__ == "__main__":
    unittest.main()
