import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import EXAMPLE
from tests.test_deliver import CLEAN_SPEC, TESTS
from tests.test_verify import DOLLAR_BUG, GOOD, TODAY

from generator.analyzer import AnalyzerFinding, AnalyzerResult
from generator.llm import LLMError
from generator.pipeline import run_pipeline
from generator.sarif import to_sarif


def answer(code):
    return json.dumps({"files": {"handlers/__init__.py": "", "handlers/user.py": code,
                                 "tests/__init__.py": "", "tests/test_user.py": TESTS}})


class Stub:
    """A chat function that returns the given answers in order."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, messages, config=None, **kw):
        self.calls.append(messages)
        a = self.answers[min(len(self.calls), len(self.answers)) - 1]
        if isinstance(a, Exception):
            raise a
        return a


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.out = Path(self._t.name) / "out"
        self.log = []

    def run_it(self, stub, **kw):
        kw.setdefault("analyzer", None)
        return run_pipeline(CLEAN_SPEC, out_dir=self.out, chat_fn=stub, today=TODAY,
                            log=self.log.append, **kw)

    def logtext(self):
        return "\n".join(self.log)


class HappyPathTests(Base):
    def test_all_five_stages(self):
        res = self.run_it(Stub(answer(GOOD)))
        self.assertEqual(res.exit_code, 0, res.error)
        self.assertEqual(res.verify.code_verdict, "passed")
        self.assertEqual(res.repair_rounds, 0)
        for stage in ("[Intake]", "[Design]", "[Build]", "[Verify]", "[Deliver]"):
            self.assertIn(stage, self.logtext())
        self.assertTrue((self.out / "handlers/user.py").exists())
        self.assertTrue((self.out / ".vishap/user.trace.json").exists())

    def test_result_to_dict_is_json(self):
        res = self.run_it(Stub(answer(GOOD)))
        json.dumps(res.to_dict())


class RepairTests(Base):
    def test_one_repair_fixes_the_dollar_bug(self):
        stub = Stub(answer(DOLLAR_BUG), answer(GOOD))
        res = self.run_it(stub)
        self.assertEqual(len(stub.calls), 2)
        self.assertEqual(res.repair_rounds, 1)
        self.assertEqual(res.verify.code_verdict, "passed")
        self.assertEqual(res.exit_code, 0)
        feedback = stub.calls[1][-1]["content"]
        self.assertIn("trailing newline", feedback)
        self.assertIn("<<<PROBLEMS", feedback)
        self.assertEqual(stub.calls[1][-2]["role"], "assistant")

    def test_repairs_zero_never_asks_again(self):
        stub = Stub(answer(DOLLAR_BUG))
        res = self.run_it(stub, repairs=0)
        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(res.verify.code_verdict, "failed")
        self.assertEqual(res.exit_code, 0)          # no gate: written, reported
        self.assertTrue((self.out / "handlers/user.py").exists())

    def test_stops_after_the_limit(self):
        stub = Stub(answer(DOLLAR_BUG))
        res = self.run_it(stub, repairs=2)
        self.assertEqual(len(stub.calls), 3)
        self.assertEqual(res.repair_rounds, 2)
        self.assertEqual(res.verify.code_verdict, "failed")

    def test_failed_repair_call_keeps_the_last_files(self):
        stub = Stub(answer(DOLLAR_BUG), LLMError("rate limited"))
        res = self.run_it(stub)
        self.assertEqual(res.repair_rounds, 0)
        self.assertEqual(res.verify.code_verdict, "failed")
        self.assertIn("repair round 1 failed", self.logtext())

    def test_analyzer_findings_go_back_to_the_model(self):
        calls = []

        def analyzer(files):
            calls.append(files)
            if len(calls) == 1:
                return AnalyzerResult("failed", (AnalyzerFinding("handlers/user.py", "error", "X1", "bad thing"),))
            return AnalyzerResult("passed")

        stub = Stub(answer(GOOD))
        res = self.run_it(stub, analyzer=analyzer)
        self.assertEqual(res.repair_rounds, 1)
        self.assertIn("X1 bad thing", stub.calls[1][-1]["content"])
        self.assertEqual(res.verify.code_verdict, "passed")


class GateTests(Base):
    def test_gate_blocks_and_exits_1(self):
        res = self.run_it(Stub(answer(DOLLAR_BUG)), gate=True, repairs=0)
        self.assertEqual(res.exit_code, 1)
        self.assertFalse(self.out.exists())
        self.assertIn("BLOCKED", self.logtext())

    def test_force_writes_and_exits_0(self):
        res = self.run_it(Stub(answer(DOLLAR_BUG)), gate=True, force=True, repairs=0)
        self.assertEqual(res.exit_code, 0)
        self.assertTrue(res.deliver.forced)
        self.assertIn("FORCED", self.logtext())

    def test_gate_passes_on_good_code(self):
        res = self.run_it(Stub(answer(GOOD)), gate=True)
        self.assertEqual(res.exit_code, 0, self.logtext())


class OtherModesTests(Base):
    def test_no_llm_does_not_call_the_model(self):
        stub = Stub(AssertionError("must not be called"))
        res = run_pipeline(CLEAN_SPEC, no_llm=True, chat_fn=stub, log=self.log.append)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(stub.calls, [])
        self.assertFalse(res.llm_used)

    def test_no_llm_with_gate_fails_on_a_critical_gap(self):
        res = run_pipeline(EXAMPLE, no_llm=True, gate=True, log=self.log.append)
        self.assertEqual(res.exit_code, 1)

    def test_bad_spec_is_exit_2(self):
        bad = Path(self._t.name) / "bad.yaml"
        bad.write_text("version: 1\n", encoding="utf-8")
        res = run_pipeline(bad, out_dir=self.out, log=self.log.append)
        self.assertEqual(res.exit_code, 2)
        self.assertTrue(res.error.startswith("spec:"))

    def test_missing_spec_file_is_exit_2(self):
        res = run_pipeline(Path(self._t.name) / "nope.yaml", out_dir=self.out)
        self.assertEqual((res.exit_code, res.error[:5]), (2, "spec:"))

    def test_model_error_is_exit_2(self):
        res = self.run_it(Stub(LLMError("no network")))
        self.assertEqual(res.exit_code, 2)
        self.assertTrue(res.error.startswith("build:"))

    def test_unusable_answer_is_exit_2(self):
        res = self.run_it(Stub("not json at all"))
        self.assertEqual(res.exit_code, 2)

    def test_no_output_folder_is_exit_2(self):
        res = run_pipeline(CLEAN_SPEC, chat_fn=Stub(answer(GOOD)), analyzer=None, today=TODAY)
        self.assertEqual(res.exit_code, 2)
        self.assertIn("--out", res.error)

    def test_allow_write_false_touches_nothing(self):
        res = self.run_it(Stub(answer(GOOD)), allow_write=False)
        self.assertEqual(res.exit_code, 0)
        self.assertFalse(self.out.exists())
        self.assertTrue(res.deliver.dry_run)

    def test_dry_run(self):
        res = self.run_it(Stub(answer(GOOD)), dry_run=True)
        self.assertFalse(self.out.exists())
        self.assertIn("+++ b/handlers/user.py", res.deliver.diff)


class SarifTests(Base):
    def test_sarif_has_the_failed_requirement_with_its_spec_line(self):
        res = self.run_it(Stub(answer(DOLLAR_BUG)), repairs=0)
        s = to_sarif(res, "spec.yaml")
        self.assertEqual(s["version"], "2.1.0")
        results = s["runs"][0]["results"]
        r1 = [r for r in results if r["ruleId"] == "requirement/R1"]
        self.assertTrue(r1)
        self.assertEqual(r1[0]["level"], "error")
        self.assertIn("startLine", r1[0]["locations"][0]["physicalLocation"]["region"])

    def test_sarif_lists_gaps(self):
        res = run_pipeline(EXAMPLE, no_llm=True)
        results = to_sarif(res, "spec.yaml")["runs"][0]["results"]
        self.assertTrue(any(r["ruleId"].startswith("gap/") and r["level"] == "error" for r in results))


if __name__ == "__main__":
    unittest.main()
