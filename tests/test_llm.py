import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tests.helpers  # noqa: F401  (puts src on the path)

from generator.llm import LLMConfig, LLMConfigError, LLMError, chat, config_from_env

KEY = "sk-test-secret-123"


class Stub:
    """A local stand-in for an OpenAI-compatible endpoint."""

    def __init__(self):
        self.status = 200
        self.body = json.dumps({"choices": [{"message": {"content": "hello"}}]}).encode()
        self.delay = 0.0
        self.requests = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                stub.requests.append({
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": json.loads(self.rfile.read(length) or b"{}"),
                })
                if stub.delay:
                    time.sleep(stub.delay)
                try:
                    self.send_response(stub.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(stub.body)))
                    self.end_headers()
                    self.wfile.write(stub.body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the client gave up first (timeout test)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.stub = Stub()
        self.cfg = LLMConfig(url=self.stub.url, model="m1", key=KEY, timeout=5)

    def tearDown(self):
        self.stub.close()

    def test_returns_the_first_choice_text(self):
        self.assertEqual(chat([{"role": "user", "content": "hi"}], self.cfg), "hello")

    def test_request_shape(self):
        chat([{"role": "user", "content": "hi"}], self.cfg, max_tokens=100)
        req = self.stub.requests[0]
        self.assertEqual(req["path"], "/v1/chat/completions")
        self.assertEqual(req["headers"]["Authorization"], f"Bearer {KEY}")
        self.assertEqual(req["body"], {
            "model": "m1",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 100,
        })

    def test_trailing_slash_in_url(self):
        cfg = LLMConfig(url=self.stub.url + "/", model="m1", key=KEY, timeout=5)
        chat([{"role": "user", "content": "x"}], cfg)
        self.assertEqual(self.stub.requests[0]["path"], "/v1/chat/completions")

    def test_no_key_no_authorization_header(self):
        cfg = LLMConfig(url=self.stub.url, model="m1", key="", timeout=5)
        chat([{"role": "user", "content": "x"}], cfg)
        self.assertNotIn("Authorization", self.stub.requests[0]["headers"])

    def test_http_error_keeps_status_and_hides_key(self):
        self.stub.status = 401
        self.stub.body = json.dumps({"error": f"bad key {KEY}"}).encode()
        with self.assertRaises(LLMError) as cm:
            chat([{"role": "user", "content": "x"}], self.cfg)
        self.assertEqual(cm.exception.status, 401)
        self.assertNotIn(KEY, str(cm.exception))
        self.assertIn("[key]", str(cm.exception))

    def test_not_a_chat_completion(self):
        self.stub.body = b'{"ok": true}'
        with self.assertRaises(LLMError):
            chat([{"role": "user", "content": "x"}], self.cfg)

    def test_not_json(self):
        self.stub.body = b"<html>gateway</html>"
        with self.assertRaises(LLMError):
            chat([{"role": "user", "content": "x"}], self.cfg)

    def test_empty_text(self):
        self.stub.body = json.dumps({"choices": [{"message": {"content": "  "}}]}).encode()
        with self.assertRaises(LLMError):
            chat([{"role": "user", "content": "x"}], self.cfg)

    def test_empty_text_explains_why(self):
        self.stub.body = json.dumps({
            "choices": [{"finish_reason": "length",
                         "message": {"content": "", "reasoning_content": "x" * 50}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 8000},
        }).encode()
        with self.assertRaises(LLMError) as cm:
            chat([{"role": "user", "content": "x"}], self.cfg)
        msg = str(cm.exception)
        self.assertIn("finish_reason=length", msg)
        self.assertIn("completion_tokens=8000", msg)
        self.assertIn("reasoning_content of 50 chars", msg)
        self.assertIn("token limit ran out", msg)
        self.assertNotIn("xxxxx", msg)

    def test_null_content(self):
        self.stub.body = json.dumps({"choices": [{"finish_reason": "stop",
                                                  "message": {"content": None}}]}).encode()
        with self.assertRaises(LLMError) as cm:
            chat([{"role": "user", "content": "x"}], self.cfg)
        self.assertIn("finish_reason=stop", str(cm.exception))

    def test_timeout(self):
        self.stub.delay = 1.0
        cfg = LLMConfig(url=self.stub.url, model="m1", key=KEY, timeout=0.2)
        with self.assertRaises(LLMError) as cm:
            chat([{"role": "user", "content": "x"}], cfg)
        self.assertIn("no answer within", str(cm.exception))

    def test_unreachable(self):
        port = self.stub.server.server_address[1]
        self.stub.close()
        cfg = LLMConfig(url=f"http://127.0.0.1:{port}/v1", model="m1", key=KEY, timeout=2)
        with self.assertRaises(LLMError) as cm:
            chat([{"role": "user", "content": "x"}], cfg)
        self.assertIn("not reachable", str(cm.exception))
        self.stub = Stub()  # so tearDown has something to close


class ConfigTests(unittest.TestCase):
    BASE = {"CUSTOM_LLM_URL": "https://api.example.com/v1",
            "CUSTOM_LLM_MODEL": "m1", "CUSTOM_LLM_KEY": KEY}

    def test_good_env(self):
        cfg = config_from_env(dict(self.BASE))
        self.assertEqual(cfg.endpoint, "https://api.example.com/v1/chat/completions")
        self.assertEqual(cfg.key, KEY)

    def test_key_not_in_repr(self):
        self.assertNotIn(KEY, repr(config_from_env(dict(self.BASE))))

    def test_url_required_no_default(self):
        env = dict(self.BASE)
        del env["CUSTOM_LLM_URL"]
        with self.assertRaises(LLMConfigError):
            config_from_env(env)

    def test_model_required(self):
        env = dict(self.BASE)
        del env["CUSTOM_LLM_MODEL"]
        with self.assertRaises(LLMConfigError):
            config_from_env(env)

    def test_plain_http_only_for_localhost(self):
        for url, ok in (("http://api.example.com/v1", False),
                        ("http://localhost:11434/v1", True),
                        ("http://127.0.0.1:11434/v1", True),
                        ("ftp://api.example.com", False),
                        ("https://user:pw@api.example.com/v1", False)):
            with self.subTest(url=url):
                env = dict(self.BASE, CUSTOM_LLM_URL=url)
                if ok:
                    config_from_env(env)
                else:
                    with self.assertRaises(LLMConfigError):
                        config_from_env(env)

    def test_other_provider_rejected(self):
        with self.assertRaises(LLMConfigError):
            config_from_env(dict(self.BASE, VISHAP_LLM_PROVIDER="deepseek"))

    def test_empty_key_for_a_remote_url_is_a_config_error(self):
        for key in ("", "   "):
            with self.subTest(key=key):
                with self.assertRaises(LLMConfigError) as cm:
                    config_from_env(dict(self.BASE, CUSTOM_LLM_KEY=key))
                self.assertIn("CUSTOM_LLM_KEY is not set", str(cm.exception))

    def test_key_that_is_not_a_key(self):
        for key in ("sk-abc def", "sk-ключ", "x" * 201, "line1\nline2"):
            with self.subTest(key=key[:20]):
                with self.assertRaises(LLMConfigError) as cm:
                    config_from_env(dict(self.BASE, CUSTOM_LLM_KEY=key))
                self.assertIn("does not look like an API key", str(cm.exception))
                self.assertNotIn(key, str(cm.exception))

    def test_key_may_be_empty(self):
        env = dict(self.BASE, CUSTOM_LLM_URL="http://localhost:11434/v1")
        del env["CUSTOM_LLM_KEY"]
        self.assertEqual(config_from_env(env).key, "")


if __name__ == "__main__":
    unittest.main()
