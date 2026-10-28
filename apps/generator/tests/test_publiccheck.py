"""GENERATOR_PUBLIC_CHECK: the spec check is open, generating needs the token (one Render service, two uses)."""
import http.client
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from tests.test_pipeline import Stub, answer
from tests.test_server import SPEC_TEXT
from tests.test_verify import GOOD, TODAY

from generator import main as server
from generator.config import LOOPBACK, public_check

HOST = "gen.example.onrender.com"
TOKEN = "t" * 24


class EnvTests(unittest.TestCase):
    def test_only_exactly_1_turns_it_on(self):
        for value, want in (("1", True), ("0", False), ("yes", False)):
            with mock.patch.dict(os.environ, {"GENERATOR_PUBLIC_CHECK": value}):
                self.assertIs(public_check(), want)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(public_check())

    def test_serve_needs_a_token_even_with_public_check(self):
        with mock.patch.dict(os.environ, {"GENERATOR_PUBLIC_CHECK": "1"}, clear=True):
            self.assertEqual(server.serve("0.0.0.0", 0), 2)

    def test_serve_passes_open_check_only_with_a_token(self):
        class Stop:
            def __init__(self, *a):
                pass
            def serve_forever(self):
                raise KeyboardInterrupt
            def server_close(self):
                pass
        for env, want in (({"GENERATOR_PUBLIC_CHECK": "1", "GENERATOR_API_TOKEN": TOKEN}, True),
                          ({"GENERATOR_API_TOKEN": TOKEN}, False)):
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(server, "ThreadingHTTPServer", Stop), \
                    mock.patch.object(server, "make_handler") as make:
                self.assertEqual(server.serve("0.0.0.0", 0), 0)
            self.assertIs(make.call_args.kwargs["open_check"], want)
            self.assertFalse(make.call_args.kwargs["check_only"])


class OneServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub = Stub(answer(GOOD))
        handler = server.make_handler(TOKEN, set(LOOPBACK) | {HOST}, client_llm=False, loopback=False, open_check=True,
                                      run_kwargs={"chat_fn": cls.stub, "analyzer": None, "today": TODAY})
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, method, path, body=None, token=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        headers = {"Host": HOST}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        c.request(method, path, body=data, headers=headers)
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, raw

    def test_status_says_both(self):
        status, out = self.call("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(out["token_required"])
        self.assertTrue(out["public_check"])
        self.assertFalse(out["check_only"])

    def test_the_check_is_open(self):
        status, out = self.call("POST", "/api/check", {"spec": SPEC_TEXT})
        self.assertEqual(status, 200, out)
        self.assertEqual(len(out["requirements"]), 6)

    def test_a_wrong_token_on_the_check_is_still_open(self):
        self.assertEqual(self.call("POST", "/api/check", {"spec": SPEC_TEXT}, token="wrong")[0], 200)

    def test_generating_needs_the_token(self):
        for path in ("/api/generate", "/api/generate/async"):
            self.assertEqual(self.call("POST", path, {"spec": SPEC_TEXT})[0], 401, path)
            self.assertEqual(self.call("POST", path, {"spec": SPEC_TEXT}, token="wrong")[0], 401, path)
        self.assertEqual(self.stub.calls, [])

    def test_generating_with_the_token_runs(self):
        status, out = self.call("POST", "/api/generate", {"spec": SPEC_TEXT}, token=TOKEN)
        self.assertEqual(status, 200, out)
        self.assertEqual(out["verify"]["code_verdict"], "passed")

    def test_jobs_need_the_token(self):
        self.assertEqual(self.call("GET", "/api/jobs/abc")[0], 401)

    def test_unknown_paths_are_404_not_401(self):
        self.assertEqual(self.call("POST", "/api/other", {})[0], 404)

    def test_a_check_cannot_carry_model_settings(self):
        status, _ = self.call("POST", "/api/check", {"spec": SPEC_TEXT, "llm": {"provider": "x", "model": "m", "key": "k"}})
        self.assertEqual(status, 403)


class WithoutOpenCheckTests(unittest.TestCase):
    def test_the_check_needs_the_token_when_it_is_not_open(self):
        handler = server.make_handler(TOKEN, set(LOOPBACK) | {HOST}, client_llm=False, loopback=False)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=30)
            c.request("POST", "/api/check", body=json.dumps({"spec": SPEC_TEXT}).encode(),
                      headers={"Host": HOST, "Content-Type": "application/json"})
            self.assertEqual(c.getresponse().status, 401)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
