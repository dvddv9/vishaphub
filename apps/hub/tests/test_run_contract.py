"""The HTTP contract of `POST /run`: what the page reads, and what it must never read.

The page shows a verdict, a summary, findings, a patch, proof lines, questions and two
check states. Whatever happens inside, those keys keep their meaning — and a run that
did not pass says so with an `error` the page can print.
"""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from hub import local, proposal
from hub.server import Handler

GOOD = {
    "calc/__init__.py": "def add(a, b):\n    return a + b\n",
    "test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
}
SPEC = {"entry": "calc", "files": ["calc/__init__.py", "test_calc.py"],
        "exports": ["add"], "tests": ["test_calc.py"]}


def fake(**over):
    payload = {"ok": True, "model": "test-model", "verdict": "SAFE", "findings": [],
               "patch": {}, "questions": [], "proof": [], "summary": "looks fine"}
    payload.update(over)
    return payload


class RunCase(unittest.TestCase):
    def setUp(self):
        from hub import limits, server as server_module
        self._saved_limits = dict(server_module.LIMITERS)
        for kind in server_module.LIMITERS:
            server_module.LIMITERS[kind] = limits.RateLimiter(0)
        self.addCleanup(lambda: server_module.LIMITERS.update(self._saved_limits))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def call(self, path, body):
        data = json.dumps(body).encode()
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())


class WithoutKeyTests(RunCase):
    def setUp(self):
        super().setUp()
        import os
        from unittest import mock
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        os.environ.pop("VISHAP_HUB_LLM_KEY", None)
        self.addCleanup(patcher.stop)

    def test_a_run_that_cannot_ask_the_model_says_so(self):
        status, out = self.call("/run", {"spec": "name: demo\n", "material": "x = 1"})
        assert status == 502
        assert out["ok"] is False
        assert "no model key" in out["error"]
        assert out["steps"][0]["stage"] == "generator"


class ContractTests(RunCase):
    def test_the_page_gets_every_key_it_renders(self):
        from unittest import mock
        with mock.patch.object(proposal, "propose", lambda **kw: fake(
                patch={"app.py": "print(1)\n"}, proof=["python app.py"], summary="fine")):
            with mock.patch.object(local, "validate_code", lambda files, spec: {
                    "ok": True, "report": {"verdict": "PASS", "finding_count": 0, "checks": []}}):
                status, out = self.call("/run", {"spec": "name: demo\n", "api_key": "k"})

        assert status == 200
        for key in ("ok", "verdict", "summary", "findings", "patch", "questions", "proof",
                    "checks", "plan", "steps", "trace", "model_verdict", "rules_verdict"):
            assert key in out, key
        assert out["verdict"] == "PASS"
        assert out["patch"] == {"app.py": "print(1)\n"}
        assert out["checks"]["generator"]["files"] == 1
        assert out["checks"]["validator"]["verdict"] == "PASS"

    def test_material_alone_plans_an_analysis(self):
        status, out = self.call("/run", {"material": "x = 1"})
        assert status == 200
        assert out["plan"]["stages"] == ["analyser"]

    def test_a_question_alone_plans_one_model_answer(self):
        from unittest import mock
        with mock.patch.object(proposal, "propose", lambda **kw: fake(summary="it depends")):
            status, out = self.call("/run", {"question": "what is this?", "api_key": "k"})
        assert status == 200
        assert out["plan"]["stages"] == ["generator"]
        assert out["plan"]["partial"] is True

    def test_an_unknown_intent_is_a_bad_request(self):
        status, out = self.call("/run", {"spec": "x", "intent": "do something clever"})
        assert status == 400
        assert "cannot route" in out["error"]

    def test_the_patch_is_analysed_and_reported(self):
        from unittest import mock
        sqli = "cur.execute(\"select * from t where a = \" + x)\n"
        with mock.patch.object(proposal, "propose", lambda **kw: fake(patch={"app.py": sqli})):
            status, out = self.call("/run", {"spec": "name: demo\n", "api_key": "k",
                                             "intent": "generate+analyse"})
        assert status == 200
        assert out["checks"]["analyser"]["verdict"] == "REQUIRES_REVIEW"
        assert any(f.get("source") == "patch:app.py" for f in out["checks"]["analyser"]["findings"])


if __name__ == "__main__":
    unittest.main()
