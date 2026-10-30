"""Changes made after the first real run (Sonnet 5.5 on Render): what the run showed and the checks that follow."""
import dataclasses
import unittest
from unittest import mock

from tests.helpers import EXAMPLE
from tests.test_checks import prepare
from tests.test_verify import GOOD, TODAY, run

from generator.pipeline import cost
from generator.pipeline.design import design
from generator.pipeline.generate import build_messages
from generator.pipeline.intake import requirements_from
from generator.pipeline.verify import BUG_ERRORS, _judge
from generator.tools import environment
from generator.tools.analyzer import AnalyzerResult
from generator.tools.assumptions import find_assumptions
from generator.tools.quality_gate import Gate, KNOWN, evaluate_gate, parse_gate
from generator.tools.report import render_markdown
from generator.tools.spec import load_spec


def accept(error=None, status=200):
    return {"expect": "accept"}, {"error": error, "status": status, "marker_seen": False}


class JudgeTests(unittest.TestCase):
    def test_a_code_bug_on_a_valid_input_fails(self):
        for name in ("TypeError", "AttributeError", "NameError", "IndexError"):
            self.assertEqual(_judge(*accept(name), {400, 422})[0], "fail", name)

    def test_a_missing_database_is_inconclusive_not_a_pass(self):
        for name in ("OperationalError", "ConnectionRefusedError", "FileNotFoundError", "KeyError"):
            status, detail = _judge(*accept(name), {400, 422})
            self.assertEqual(status, "inconclusive", name)
            self.assertIn(name, detail)

    def test_a_server_error_on_a_valid_input_is_inconclusive(self):
        self.assertEqual(_judge(*accept(None, 500), {400, 422})[0], "inconclusive")
        self.assertEqual(_judge(*accept(None, 200), {400, 422})[0], "pass")
        self.assertEqual(_judge(*accept(None, 404), {400, 422})[0], "pass")
        self.assertEqual(_judge(*accept(None, 400), {400, 422})[0], "fail")

    def test_a_reject_attack_that_raises_still_fails(self):
        req = {"expect": "reject"}
        self.assertEqual(_judge(req, {"error": "OperationalError", "status": None, "marker_seen": False}, {400})[0], "fail")

    def test_the_bug_list_has_only_programming_errors(self):
        self.assertTrue({"TypeError", "NameError"} <= BUG_ERRORS)
        self.assertFalse({"OperationalError", "KeyError", "OSError"} & BUG_ERRORS)


class VerifyUsesItTests(unittest.TestCase):
    def test_a_type_error_in_the_code_fails_r1(self):
        code = GOOD.replace('    if name not in USERS:', '    name = name + 1\n    if name not in USERS:')
        res = run(code=code)
        r1 = [r for r in res.requirements if r.id == "R1"][0]
        self.assertEqual(r1.status, "failed", [e.to_dict() for e in r1.evidence])

    def test_inconclusive_is_not_counted_as_proof(self):
        from generator.pipeline.verdict import Evidence, decide_requirement
        only = [Evidence("attack", "length 1", "inconclusive", "raised OperationalError")]
        self.assertEqual(decide_requirement(only)[0], "needs_verification")
        with_test = only + [Evidence("model-test", "test_r1", "pass", "")]
        self.assertEqual(decide_requirement(with_test)[0], "passed")


class AssumptionTests(unittest.TestCase):
    def test_real_comments_only_with_line_numbers(self):
        code = "x = 1  # assumption: G1 only GET\n# assumption: two\n# lines\ny = '# assumption: in a string'\n# assumption: end\n"
        got = find_assumptions({"a.py": code, "b.txt": "# assumption: not python"})
        self.assertEqual([(a["line"], a["text"]) for a in got], [(1, "G1 only GET"), (2, "two lines"), (5, "end")])
        self.assertEqual({a["file"] for a in got}, {"a.py"})

    def test_broken_python_is_skipped(self):
        self.assertEqual(find_assumptions({"a.py": "def (:\n  # assumption: x\n"}), [])


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        spec = load_spec(EXAMPLE)
        self.reqs = requirements_from(spec)
        self.spec = spec
        self.design = design(spec, self.reqs)

    def missing(self):
        return mock.patch.object(environment.importlib.util, "find_spec", return_value=None)

    def test_status_follows_find_spec(self):
        with self.missing():
            self.assertEqual(environment.library_status(["flask", "spring-boot"]), {"flask": "missing"})
        with mock.patch.object(environment.importlib.util, "find_spec", return_value=object()):
            self.assertEqual(environment.library_status(["flask"]), {"flask": "installed"})

    def test_the_build_message_names_a_missing_library(self):
        planned = {lib for f in self.design.files for lib in f.library_check}
        self.assertIn("flask", planned)
        with self.missing():
            text = build_messages(self.spec, self.reqs, self.design)[1]["content"]
        self.assertIn("ENVIRONMENT:", text)
        self.assertIn("flask: NOT installed", text)
        self.assertIn("WSGI", text)

    def test_an_installed_library_is_just_listed(self):
        with mock.patch.object(environment.importlib.util, "find_spec", return_value=object()):
            text = build_messages(self.spec, self.reqs, self.design)[1]["content"]
        self.assertIn("- flask: installed", text)
        self.assertNotIn("NOT installed", text)

    def test_no_planned_library_no_section(self):
        env = {"python": "3.12.0", "libraries": {}}
        self.assertEqual(environment.environment_lines(env), [])
        self.assertEqual(environment.fallbacks(env), [])
        self.assertEqual(environment.fallbacks({"libraries": {"flask": "missing", "x": "installed"}}), ["flask"])

    def test_the_build_prompt_tells_the_model_about_the_section(self):
        from generator.pipeline.prompts import load_prompt
        text = load_prompt("03_build")
        self.assertIn("ENVIRONMENT", text)
        self.assertIn("NOT installed", text)


class GateAndReportTests(unittest.TestCase):
    def test_require_analyzer_blocks_a_skipped_analyzer(self):
        p = prepare()
        v = dataclasses.replace(p["verify"], analyzer=AnalyzerResult("skipped", note="command not found: vishap"))
        self.assertFalse(any("analyzer did not run" in r for r in evaluate_gate(p["design"], p["build"], v).reasons))
        res = evaluate_gate(p["design"], p["build"], v, Gate(require_analyzer=True))
        self.assertTrue(any("analyzer did not run: command not found: vishap" in r for r in res.reasons), res.reasons)
        v2 = dataclasses.replace(p["verify"], analyzer=AnalyzerResult("passed"))
        self.assertFalse(any("analyzer did not run" in r for r in evaluate_gate(p["design"], p["build"], v2, Gate(require_analyzer=True)).reasons))
        v3 = dataclasses.replace(p["verify"], analyzer=None)
        self.assertTrue(any("analyzer did not run" in r for r in evaluate_gate(p["design"], p["build"], v3, Gate(require_analyzer=True)).reasons))

    def test_the_key_is_known_and_checked(self):
        self.assertIn("require_analyzer", KNOWN)
        self.assertTrue(parse_gate({"require_analyzer": True}).require_analyzer)
        from generator.tools.quality_gate import QualityGateError
        with self.assertRaises(QualityGateError):
            parse_gate({"require_analyzer": "yes"})
        self.assertTrue(Gate().to_dict()["require_analyzer"] is False)


class PipelineTests(unittest.TestCase):
    def run_pipeline(self, code):
        from tests.test_deliver import CLEAN_SPEC
        from tests.test_pipeline import Stub, answer
        from generator.pipeline.orchestrator import run_pipeline
        return run_pipeline(CLEAN_SPEC, chat_fn=Stub(answer(code)), today=TODAY, analyzer=None, allow_write=False)

    def test_assumptions_and_environment_reach_the_result_and_the_report(self):
        code = GOOD.replace("def app(", "# assumption: G1 only GET /user is exposed\ndef app(")
        res = self.run_pipeline(code)
        d = res.to_dict()
        self.assertEqual([a["text"] for a in d["assumptions"]], ["G1 only GET /user is exposed"])
        self.assertIn("python", d["environment"])
        md = render_markdown(res, "spec.yaml")
        self.assertIn("## Assumptions", md)
        self.assertIn("G1 only GET /user is exposed", md)
        self.assertIn("**Analyzer:** did not run", md)
        self.assertIn("Cost: not priced", md)

    def test_usage_says_whether_the_cost_is_priced(self):
        res = self.run_pipeline(GOOD)
        self.assertIs(res.usage["cost_known"], False)
        with mock.patch.dict("os.environ", {"GENERATOR_PRICE_IN": "3", "GENERATOR_PRICE_OUT": "15"}):
            self.assertIs(res.usage["cost_known"], True)
            self.assertTrue(cost.prices_set())
        self.assertFalse(cost.prices_set())


if __name__ == "__main__":
    unittest.main()
