import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests import helpers  # noqa: F401
from tests.test_deliver import CLEAN_SPEC
from tests.test_pipeline import Stub, answer
from tests.test_verify import GOOD, TODAY

from generator import cli
from generator.llm import LLMError
from generator.pipeline.orchestrator import run_pipeline
from generator.pipeline.batch import batch_exit_code, find_specs, out_name, run_batch
from generator.storage.history import load_history


class BatchTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name)
        self.specs = self.root / "specs"
        self.specs.mkdir()
        for name in ("one", "two"):
            shutil.copy(CLEAN_SPEC, self.specs / f"{name}.yaml")
        self.out = self.root / "out"
        self.kw = dict(chat_fn=Stub(answer(GOOD)), today=TODAY, analyzer=None, text_check=False)

    def test_find_specs_takes_files_and_folders_once(self):
        found = find_specs([self.specs, self.specs / "one.yaml"])
        self.assertEqual([p.name for p in found], ["one.yaml", "two.yaml"])

    def test_out_names_are_safe_and_unique(self):
        taken = set()
        self.assertEqual(out_name(Path("a b.yaml"), taken), "a-b")
        self.assertEqual(out_name(Path("a b.yml"), taken), "a-b-2")

    def test_each_spec_gets_its_own_folder(self):
        rows = run_batch(find_specs([self.specs]), self.out, workers=2, **self.kw)
        self.assertEqual([r.status for r in rows], ["done", "done"])
        for name in ("one", "two"):
            self.assertTrue((self.out / name / "handlers/user.py").exists())
            self.assertEqual(len(load_history(self.out / name)), 1)
        self.assertEqual(batch_exit_code(rows), 0)

    def test_finished_specs_are_skipped_unless_again(self):
        run_batch(find_specs([self.specs]), self.out, **self.kw)
        rows = run_batch(find_specs([self.specs]), self.out, **self.kw)
        self.assertEqual([r.status for r in rows], ["skipped", "skipped"])
        rows = run_batch(find_specs([self.specs]), self.out, again=True, **self.kw)
        self.assertEqual([r.status for r in rows], ["done", "done"])

    def test_one_failure_does_not_stop_the_others(self):
        (self.specs / "bad.yaml").write_text("not: [a spec", encoding="utf-8")
        rows = run_batch(find_specs([self.specs]), self.out, **self.kw)
        status = {Path(r.spec).stem: r.status for r in rows}
        self.assertEqual(status, {"bad": "error", "one": "done", "two": "done"})
        self.assertEqual(batch_exit_code(rows), 2)

    def test_model_failure_is_an_error_row(self):
        kw = dict(self.kw, chat_fn=Stub(LLMError("down")))
        rows = run_batch(find_specs([self.specs]), self.out, **kw)
        self.assertEqual({r.status for r in rows}, {"error"})
        self.assertIn("down", rows[0].error)


class ValidateConfigTests(unittest.TestCase):
    def test_reports_problems_without_printing_a_key(self):
        from generator.config import validate_config
        errors, warnings = validate_config({"GENERATOR_PRICE_IN": "-1", "LOG_FORMAT": "xml", "LOG_LEVEL": "LOUD",
                                            "CUSTOM_LLM_KEY": "supersecretkeyvalue"})
        self.assertEqual(len(errors), 3)
        self.assertNotIn("supersecretkeyvalue", " ".join(errors + warnings))

    def test_a_clean_environment_has_no_errors(self):
        from generator.config import validate_config
        errors, _ = validate_config({"CUSTOM_LLM_URL": "https://api.deepseek.com", "CUSTOM_LLM_MODEL": "m",
                                     "GENERATOR_PRICE_IN": "3", "GENERATOR_PRICE_OUT": "15"})
        self.assertEqual(errors, [])


class CliCommandTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_info(self):
        code, out, _ = self.run_cli("info")
        self.assertEqual(code, 0)
        self.assertIn("1 Intake -> 2 Design -> 3 Build -> 4 Verify -> 5 Deliver", out)
        self.assertIn("03_build:", out)

    def test_history_empty_and_filled(self):
        code, out, _ = self.run_cli("history", "--out", str(self.root))
        self.assertIn("no runs recorded", out)
        from generator.storage.history import add_entry
        add_entry(self.root, {"run_id": "r1", "verdict": "passed", "spec": "s.yaml", "usage": {"llm_calls": 3}})
        code, out, _ = self.run_cli("history", "--out", str(self.root))
        self.assertIn("r1", out)
        self.assertIn("calls 3", out)
        code, out, _ = self.run_cli("history", "--out", str(self.root), "--json")
        self.assertEqual(json.loads(out)[0]["run_id"], "r1")

    def test_baseline_writes_next_to_the_spec_and_the_gate_reads_it(self):
        spec = self.root / "spec.yaml"
        shutil.copy(helpers.EXAMPLE, spec)
        code, out, _ = self.run_cli("baseline", str(spec))
        self.assertEqual(code, 0)
        self.assertTrue((self.root / ".vishap/baseline.json").exists())
        from generator.tools.quality_gate import load_quality_gate
        self.assertTrue(load_quality_gate(self.root).accepted_gaps)
        code, out, _ = self.run_cli("baseline", str(spec), "--list")
        self.assertIn("accepted", out)
        self.assertNotIn("OPEN", out)

    def test_baseline_of_a_clean_spec_writes_nothing(self):
        code, out, _ = self.run_cli("baseline", str(CLEAN_SPEC), "--list")
        self.assertEqual(code, 0)

    def test_bad_spec_is_exit_2(self):
        bad = self.root / "bad.yaml"
        bad.write_text("x: [", encoding="utf-8")
        self.assertEqual(self.run_cli("baseline", str(bad))[0], 2)

    def test_batch_runs_and_prints_a_summary(self):
        import functools
        from unittest import mock
        specs = self.root / "specs"
        specs.mkdir()
        shutil.copy(CLEAN_SPEC, specs / "one.yaml")
        real = functools.partial(run_pipeline, chat_fn=Stub(answer(GOOD)), today=TODAY, analyzer=None)
        with mock.patch("generator.pipeline.batch.run_pipeline", real), \
                mock.patch.object(cli, "_default_analyzer", lambda: None):
            code, out, err = self.run_cli("batch", str(specs), "--out", str(self.root / "o"),
                                          "--no-text-check", "--json", str(self.root / "rows.json"))
        self.assertEqual(code, 0, err)
        self.assertIn("summary     1 done", out)
        self.assertEqual(json.loads((self.root / "rows.json").read_text())[0]["status"], "done")

    def test_batch_without_specs_is_exit_2(self):
        empty = self.root / "empty"
        empty.mkdir()
        code, _, err = self.run_cli("batch", str(empty), "--out", str(self.root / "o"))
        self.assertEqual(code, 2)
        self.assertIn("no spec files", err)

    def test_generate_report_file(self):
        import functools
        from unittest import mock
        spec = self.root / "spec.yaml"
        shutil.copy(CLEAN_SPEC, spec)
        real = functools.partial(run_pipeline, chat_fn=Stub(answer(GOOD)), today=TODAY)
        with mock.patch.object(cli, "run_pipeline", real), mock.patch.object(cli, "_default_analyzer", lambda: None):
            code, out, err = self.run_cli("generate", str(spec), "--out", str(self.root / "o"),
                                          "--report", str(self.root / "r.md"))
        self.assertEqual(code, 0, err)
        self.assertIn("usage       2 model call(s)", out)
        self.assertIn("**Verdict:** PASSED", (self.root / "r.md").read_text())

    def test_usage_line(self):
        line = cli.usage_line({"llm_calls": 3, "tokens_in": 100, "tokens_out": 50, "cost_usd": 0.0123,
                               "duration_s": 4.25})
        self.assertEqual(line, "3 model call(s), 100 tokens in / 50 out, 4.2 s, $0.0123")
        self.assertIn("not reported", cli.usage_line({"llm_calls": 1, "tokens_in": 0, "tokens_out": 0,
                                                      "cost_usd": 0.0, "duration_s": 1.0}))


if __name__ == "__main__":
    unittest.main()
