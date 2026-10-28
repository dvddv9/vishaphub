import contextlib
import functools
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import EXAMPLE
from tests.test_deliver import CLEAN_SPEC
from tests.test_pipeline import Stub, answer
from tests.test_verify import DOLLAR_BUG, GOOD

from generator import cli
from generator.pipeline import run_pipeline


class CliTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        self.out = self.tmp / "out"

    def run_cli(self, argv, stub=None):
        stub = stub or Stub(answer(GOOD))
        real = functools.partial(run_pipeline, chat_fn=stub)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "run_pipeline", real), \
                mock.patch.object(cli, "_default_analyzer", lambda: None), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_generate_writes_and_reports(self):
        code, out, err = self.run_cli(["generate", str(CLEAN_SPEC), "--out", str(self.out)])
        self.assertEqual(code, 0, err)
        self.assertIn("verdict     PASSED", out)
        self.assertIn("rollback: vishap-generator rollback", out)
        self.assertTrue((self.out / "handlers/user.py").exists())

    def test_gate_exit_code_1_and_nothing_written(self):
        code, out, err = self.run_cli(
            ["generate", str(CLEAN_SPEC), "--out", str(self.out), "--gate", "--repairs", "0"],
            Stub(answer(DOLLAR_BUG)))
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED", out)
        self.assertFalse(self.out.exists())

    def test_force_without_gate_is_a_usage_error(self):
        code, _, err = self.run_cli(["generate", str(CLEAN_SPEC), "--out", str(self.out), "--force"])
        self.assertEqual(code, 2)
        self.assertIn("--gate", err)

    def test_out_is_required_unless_no_llm(self):
        code, _, err = self.run_cli(["generate", str(CLEAN_SPEC)])
        self.assertEqual(code, 2)
        self.assertIn("--out", err)
        code, out, _ = self.run_cli(["generate", str(CLEAN_SPEC), "--no-llm"])
        self.assertEqual(code, 0)

    def test_dry_run_prints_the_diff(self):
        code, out, _ = self.run_cli(["generate", str(CLEAN_SPEC), "--out", str(self.out), "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("+++ b/handlers/user.py", out)
        self.assertFalse(self.out.exists())

    def test_json_and_sarif_files(self):
        j, s = self.tmp / "r.json", self.tmp / "r.sarif"
        code, _, _ = self.run_cli(["generate", str(CLEAN_SPEC), "--out", str(self.out),
                                   "--json", str(j), "--sarif", str(s)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(j.read_text(encoding="utf-8"))["verify"]["code_verdict"], "passed")
        self.assertEqual(json.loads(s.read_text(encoding="utf-8"))["version"], "2.1.0")

    def test_bad_spec_prints_the_error(self):
        bad = self.tmp / "bad.yaml"
        bad.write_text("version: 1\n", encoding="utf-8")
        code, _, err = self.run_cli(["generate", str(bad), "--out", str(self.out)])
        self.assertEqual(code, 2)
        self.assertIn("error: spec:", err)

    def test_rollback_command(self):
        self.run_cli(["generate", str(CLEAN_SPEC), "--out", str(self.out)])
        run_id = next((self.out / ".vishap/runs").iterdir()).name
        code, out, _ = self.run_cli(["rollback", run_id, "--out", str(self.out)])
        self.assertEqual(code, 0)
        self.assertIn("removed     handlers/user.py", out)
        self.assertFalse((self.out / "handlers/user.py").exists())
        code, _, err = self.run_cli(["rollback", run_id, "--out", str(self.out)])
        self.assertEqual(code, 2)
        self.assertIn("already rolled back", err)

    def test_example_spec_has_a_critical_gap_the_gate_reports(self):
        code, out, _ = self.run_cli(["generate", str(EXAMPLE), "--no-llm", "--gate"])
        self.assertEqual(code, 1)
        self.assertIn("G1 critical", out)

    def test_require_coverage_needs_gate(self):
        code, _, err = self.run_cli(["generate", str(CLEAN_SPEC), "--out", str(self.out), "--require-coverage"])
        self.assertEqual(code, 2)
        self.assertIn("--gate", err)

    def test_init_writes_a_spec_that_loads_and_has_no_open_gaps(self):
        path = self.tmp / "new.yaml"
        code, out, _ = self.run_cli(["init", str(path)])
        self.assertEqual(code, 0)
        code, out, _ = self.run_cli(["generate", str(path), "--no-llm", "--gate"])
        self.assertEqual(code, 0, out)
        self.assertIn("gaps: 0 critical", out)
        code, _, err = self.run_cli(["init", str(path)])
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)

    def test_no_command_is_an_error(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main([])


if __name__ == "__main__":
    unittest.main()

