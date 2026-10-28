"""0.6.0 surfaces: the REST API fields and the command-line flags."""
import contextlib
import functools
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import write_spec
from tests.test_deliver import CLEAN_SPEC
from tests.test_pipeline import Stub, answer
from tests.test_server import SPEC_TEXT, ServerCase
from tests.test_verify import GOOD

from generator import cli
from generator.pipeline.orchestrator import run_pipeline

BARE = ('version: 1\nupdated: 2026-10-27\ntext: |\n  Do a thing.\n'
        'must_never:\n  - id: a\n    text: "Never print secrets"\n')


class DepthApiTests(ServerCase):
    def test_effort_and_candidates_reach_the_run(self):
        status, out = self.post("/api/generate", {"spec": SPEC_TEXT, "effort": "quick"})
        self.assertEqual(status, 200, out)
        self.assertEqual(out["effort"], "quick")
        self.assertEqual(len(out["threats"]), 6)
        status, out = self.post("/api/generate", {"spec": SPEC_TEXT, "candidates": 2})
        self.assertEqual(status, 200, out)
        self.assertEqual(len(out["candidates"]), 2)
        self.assertEqual(sum(c["chosen"] for c in out["candidates"]), 1)

    def test_the_report_has_the_new_sections(self):
        _, out = self.post("/api/generate", {"spec": SPEC_TEXT, "candidates": 2})
        for part in ("## STRIDE", "## Candidates"):
            self.assertIn(part, out["markdown"])

    def test_bad_values_are_400(self):
        for body in ({"effort": "huge"}, {"effort": 3}, {"candidates": 0}, {"candidates": 99},
                     {"candidates": "2"}, {"candidates": True}, {"repairs": -1}):
            status, out = self.post("/api/generate", {"spec": SPEC_TEXT, **body})
            self.assertEqual(status, 400, (body, out))

    def test_strict_refusal_is_422(self):
        status, out = self.post("/api/generate", {"spec": BARE, "strict": True})
        self.assertEqual(status, 422, out)
        self.assertIn("Cannot answer reliably", out["error"])

    def test_without_strict_the_same_spec_is_not_refused(self):
        status, out = self.post("/api/check", {"spec": BARE})
        self.assertNotEqual(status, 422, out)

    def test_async_takes_the_same_fields(self):
        status, out = self.post("/api/generate/async", {"spec": SPEC_TEXT, "effort": "quick"})
        self.assertEqual(status, 202, out)
        end = time.time() + 30
        while time.time() < end:
            _, data = self.req(f"/api/jobs/{out['job']}")
            done = json.loads(data)
            if done["status"] in ("done", "failed"):
                break
            time.sleep(0.05)
        self.assertEqual(done["result"]["effort"], "quick")
        status, bad = self.post("/api/generate/async", {"spec": SPEC_TEXT, "effort": "huge"})
        self.assertEqual(status, 400, bad)
        self.assertNotIn("job", bad)


class DepthCliTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.out = Path(self._t.name) / "out"

    def run_cli(self, argv, stub=None):
        stub = stub or Stub(answer(GOOD))
        real = functools.partial(run_pipeline, chat_fn=stub)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "run_pipeline", real), \
                mock.patch.object(cli, "_default_analyzer", lambda: None), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(argv)
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue(), stub

    def gen(self, *flags, spec=CLEAN_SPEC, stub=None):
        return self.run_cli(["generate", str(spec), "--out", str(self.out), *flags], stub)

    def test_the_stride_line_is_printed(self):
        code, out, err, _ = self.gen()
        self.assertEqual(code, 0, err)
        self.assertRegex(out, r"stride\s+T covered/proven\s+I covered/proven\s+D partial")

    def test_strict_refuses_a_bare_spec(self):
        code, out, err, stub = self.gen("--strict", spec=write_spec(BARE))
        self.assertEqual(code, 2)
        self.assertIn("Cannot answer reliably", out + err)
        self.assertEqual(stub.calls, [])

    def test_effort_quick(self):
        code, out, err, stub = self.gen("--effort", "quick")
        self.assertEqual(code, 0, err)
        self.assertEqual(stub.text_calls, [])

    def test_a_bad_effort_is_a_usage_error(self):
        code, out, err, _ = self.gen("--effort", "huge")
        self.assertEqual(code, 2)
        self.assertIn("effort", err)

    def test_candidates_are_listed(self):
        code, out, err, stub = self.gen("--candidates", "2")
        self.assertEqual(code, 0, err)
        self.assertIn("candidates", out)
        self.assertIn("*", out)
        self.assertEqual(len(stub.calls), 2)

    def test_repro_with_candidates_is_refused(self):
        code, out, err, stub = self.gen("--repro", "--candidates", "2")
        self.assertEqual(code, 2)
        self.assertIn("repro", out + err)
        self.assertEqual(stub.calls, [])

    def test_batch_has_the_same_flags(self):
        with contextlib.redirect_stdout(io.StringIO()) as o, contextlib.redirect_stderr(io.StringIO()) as e:
            try:
                cli.main(["batch", "--help"])
            except SystemExit:
                pass
        text = o.getvalue() + e.getvalue()
        for flag in ("--effort", "--candidates", "--cove", "--strict", "--repro"):
            self.assertIn(flag, text)

    def test_stride_line_helper(self):
        line = cli.stride_line([{"letter": "S", "status": "covered", "proof": "proven"},
                                {"letter": "T", "status": "partial", "proof": "-"},
                                {"letter": "R", "status": "not_covered", "proof": "-"},
                                {"letter": "I", "status": "not_applicable", "proof": "-"}])
        self.assertEqual(line, "S covered/proven  T partial  R not covered")      # not applicable rows are left out


if __name__ == "__main__":
    unittest.main()
