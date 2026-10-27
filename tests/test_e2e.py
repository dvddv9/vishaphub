"""The real command line against a local stand-in for the model.

Covers what the unit tests stub out: llm.py's HTTP request, config from
the environment, the CLI entry point, exit codes and files on disk.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.helpers import ROOT
from tests.test_deliver import CLEAN_SPEC
from tests.test_pipeline import answer
from tests.test_verify import DOLLAR_BUG, GOOD


class FakeModel:
    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                fake.seen.append(json.loads(self.rfile.read(n)))
                text = fake.answers[min(len(fake.seen), len(fake.answers)) - 1]
                body = json.dumps({"choices": [{"message": {"content": text}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.out = Path(self._t.name) / "out"

    def cli(self, model, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CUSTOM_LLM")}
        env.update({"PYTHONPATH": str(ROOT / "src"), "CUSTOM_LLM_URL": model.url,
                    "CUSTOM_LLM_MODEL": "stub", "VISHAP_ANALYZER_CMD": "no-such-analyzer"})
        return subprocess.run([sys.executable, "-m", "generator", *args], env=env, cwd=self._t.name,
                              capture_output=True, text=True, encoding="utf-8", timeout=180)

    def test_generate_through_the_real_cli(self):
        model = FakeModel(answer(GOOD))
        self.addCleanup(model.close)
        p = self.cli(model, "generate", str(CLEAN_SPEC), "--out", str(self.out))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("verdict     PASSED", p.stdout)
        self.assertTrue((self.out / "handlers/user.py").exists())
        sent = model.seen[0]
        self.assertEqual(sent["model"], "stub")
        self.assertEqual(sent["messages"][0]["role"], "system")

    def test_repair_round_over_http(self):
        model = FakeModel(answer(DOLLAR_BUG), answer(GOOD))
        self.addCleanup(model.close)
        p = self.cli(model, "generate", str(CLEAN_SPEC), "--out", str(self.out), "--no-analyzer")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(len(model.seen), 2)
        self.assertIn("verdict     PASSED", p.stdout)
        self.assertIn("[Repair]", p.stdout)

    def test_gate_exit_code_through_the_process(self):
        model = FakeModel(answer(DOLLAR_BUG))
        self.addCleanup(model.close)
        p = self.cli(model, "generate", str(CLEAN_SPEC), "--out", str(self.out),
                     "--gate", "--repairs", "0", "--no-analyzer")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertFalse(self.out.exists())

    def test_missing_model_settings_is_exit_2_with_a_reason(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CUSTOM_LLM")}
        env["PYTHONPATH"] = str(ROOT / "src")
        p = subprocess.run([sys.executable, "-m", "generator", "generate", str(CLEAN_SPEC),
                            "--out", str(self.out), "--no-analyzer"], env=env, cwd=self._t.name,
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("CUSTOM_LLM_URL is not set", p.stderr)


if __name__ == "__main__":
    unittest.main()
