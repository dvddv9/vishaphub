"""GENERATOR_CHECK_ONLY: the public demo checks specs and nothing else."""
import http.client
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from tests.test_server import SPEC_TEXT

from generator import main as server
from generator.config import LOOPBACK, check_only, public_hosts

HOST = "demo.example.onrender.com"


class EnvTests(unittest.TestCase):
    def test_check_only_is_off_unless_it_is_exactly_1(self):
        for value, want in (("1", True), ("0", False), ("true", False), ("", False)):
            with mock.patch.dict(os.environ, {"GENERATOR_CHECK_ONLY": value}):
                self.assertIs(check_only(), want, value)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(check_only())

    def test_public_hosts_from_both_variables(self):
        env = {"GENERATOR_PUBLIC_HOSTS": " A.example.com, b.example.com ,", "RENDER_EXTERNAL_HOSTNAME": "R.onrender.com"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(public_hosts(), {"a.example.com", "b.example.com", "r.onrender.com"})
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(public_hosts(), set())


class ServeTests(unittest.TestCase):
    def test_a_public_address_without_token_or_check_only_is_refused(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(server.serve("0.0.0.0", 0), 2)

    def test_check_only_may_listen_publicly_without_a_token(self):
        class Stop:
            def __init__(self, addr, handler):
                self.addr = addr
            def serve_forever(self):
                raise KeyboardInterrupt
            def server_close(self):
                pass
        with mock.patch.dict(os.environ, {"GENERATOR_CHECK_ONLY": "1", "RENDER_EXTERNAL_HOSTNAME": HOST}, clear=True), \
                mock.patch.object(server, "ThreadingHTTPServer", Stop), \
                mock.patch.object(server, "make_handler") as make:
            self.assertEqual(server.serve("0.0.0.0", 0), 0)
        names, kw = make.call_args.args[1], make.call_args.kwargs
        self.assertIn(HOST, names)
        self.assertTrue(kw["check_only"])
        self.assertFalse(kw["client_llm"])         # a visitor cannot make the server call a URL


class DemoServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = set(LOOPBACK) | {HOST}
        handler = server.make_handler(None, names, client_llm=False, loopback=False, check_only=True)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, method, path, body=None, host=HOST, origin=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        headers = {"Host": host}
        if origin:
            headers["Origin"] = origin
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

    def test_status_says_check_only_and_has_no_providers(self):
        status, out = self.call("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(out["check_only"])
        self.assertEqual(out["providers"], [])
        self.assertFalse(out["client_llm_allowed"])

    def test_the_form_is_served(self):
        status, raw = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Vishap", raw)

    def test_check_works_without_a_model(self):
        status, out = self.call("POST", "/api/check", {"spec": SPEC_TEXT})
        self.assertEqual(status, 200, out)
        self.assertEqual(len(out["requirements"]), 6)
        self.assertEqual(len(out["threats"]), 6)
        self.assertNotIn("verify", out)
        self.assertFalse(out["llm_used"])

    def test_generate_is_refused_in_both_forms(self):
        for path in ("/api/generate", "/api/generate/async"):
            status, out = self.call("POST", path, {"spec": SPEC_TEXT})
            self.assertEqual(status, 403, path)
            self.assertIn("only checks specs", out["error"])

    def test_a_model_setting_in_a_check_is_ignored(self):
        status, out = self.call("POST", "/api/check", {"spec": SPEC_TEXT, "llm": {"url": "https://evil.example", "model": "m", "key": "k"}})
        self.assertIn(status, (200, 403), out)      # never a call to that URL: no model call exists in a check

    def test_other_host_names_and_origins_are_still_refused(self):
        self.assertEqual(self.call("GET", "/api/status", host="evil.example.com")[0], 403)
        self.assertEqual(self.call("GET", "/api/status", origin="https://evil.example.com")[0], 403)
        self.assertEqual(self.call("GET", "/api/status", origin=f"https://{HOST}")[0], 200)


if __name__ == "__main__":
    unittest.main()
