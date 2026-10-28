"""The mutation check: do the model's tests notice when the code is changed?"""
import ast
import json
import os
import sys
import unittest
from unittest import mock

from tests.test_deliver import CLEAN_SPEC
from tests.test_deliver import TESTS as TESTS6
from tests.test_pipeline import Stub
from tests.test_verify import GOOD, TESTS, TODAY

from generator.pipeline import mutation as mut
from generator.pipeline.candidates import Candidate, disagreements
from generator.pipeline.effort import EffortError, resolve
from generator.pipeline.generate import feedback_text
from generator.pipeline.orchestrator import run_pipeline
from generator.pipeline.verdict import Evidence, RequirementVerdict, VerifyResult
from generator.tools.questions import questions_for
from generator.tools.quality_gate import Gate, QualityGateError, evaluate_gate, parse_gate
from generator.tools.gaps import Gap
from generator.tools.report import render_markdown
from tests.test_checks import prepare

FILES = {"handlers/__init__.py": "", "handlers/user.py": GOOD, "tests/__init__.py": "", "tests/test_user.py": TESTS}
CODE, TEST = ["handlers/user.py"], ["tests/test_user.py"]

# Tests that only look at one happy answer.
WEAK = '''\
import unittest
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

from handlers.user import app


def status_of(query):
    env = {}
    setup_testing_defaults(env)
    env["QUERY_STRING"] = urlencode(query)
    seen = {}
    b"".join(app(env, lambda s, h, e=None: seen.update(status=int(s.split()[0]))))
    return seen["status"]


class T(unittest.TestCase):
    def test_r1(self):
        self.assertEqual(status_of({"name": "alice"}), 200)

    def test_r2(self):
        self.assertEqual(status_of({"name": "alice"}), 200)

    def test_r3(self):
        self.assertEqual(status_of({"name": "alice"}), 200)

    def test_r4(self):
        self.assertEqual(status_of({"name": "alice"}), 200)

    def test_r5(self):
        self.assertEqual(status_of({"name": "alice"}), 200)

    def test_r6(self):
        self.assertEqual(status_of({"name": "alice"}), 200)
'''


def run(files=None, limit=40, **kw):
    return mut.run_mutation(files or FILES, CODE, TEST, limit, python=sys.executable, **kw)


class FindTests(unittest.TestCase):
    def test_the_operators_find_what_the_first_real_run_needed(self):
        kinds = {m.kind for m in mut.find_mutants("h.py", GOOD)}
        self.assertTrue({"regex", "status", "compare", "if", "boolean", "not", "number"} <= kinds, kinds)

    def test_the_same_code_gives_the_same_mutants(self):
        a = [(m.line, m.kind, m.change) for m in mut.find_mutants("h.py", GOOD)]
        self.assertEqual(a, [(m.line, m.kind, m.change) for m in mut.find_mutants("h.py", GOOD)])
        self.assertEqual([m.index for m in mut.find_mutants("h.py", GOOD)], list(range(len(a))))

    def test_every_mutant_is_valid_python_and_differs(self):
        base = ast.unparse(ast.parse(GOOD))
        for m in mut.find_mutants("h.py", GOOD):
            changed = mut.apply(GOOD, m)
            self.assertIsNotNone(changed, m.change)
            ast.parse(changed)
            self.assertNotEqual(changed, base, m.change)

    def test_a_syntax_error_has_no_mutants(self):
        self.assertEqual(mut.find_mutants("h.py", "def (:\n"), [])

    def test_the_main_guard_and_booleans_are_left_alone(self):
        code = "if __name__ == '__main__':\n    x = True\n    y = None\n"
        self.assertEqual(mut.find_mutants("h.py", code), [])

    def test_specific_changes(self):
        changes = {m.change for m in mut.find_mutants("h.py", GOOD)}
        self.assertIn("`.fullmatch` becomes `.match`", changes)
        self.assertIn('the status "400 Bad Request" becomes "401 Bad Request"', changes)
        self.assertIn("`not` is removed", changes)

    def test_sample_is_even_and_repeatable(self):
        ms = mut.find_mutants("h.py", GOOD)
        picked = mut.sample(ms, 4)
        self.assertEqual(len(picked), 4)
        self.assertEqual(picked, mut.sample(ms, 4))
        self.assertEqual(mut.sample(ms, 100), ms)
        self.assertEqual(mut.sample(ms, 0), [])


class RunTests(unittest.TestCase):
    def test_a_check_on_good_tests_finds_the_one_the_tests_do_not_see(self):
        res = run()
        self.assertEqual(res.status, "ok", res.note)
        self.assertEqual(res.run, res.planned)
        self.assertGreaterEqual(res.score, 80)
        # `{"alice": 1}`: the answer body is a constant, so changing the stored id changes nothing a test can see.
        # This is an equivalent mutant: a survivor that is not a weak test. The report says such cases exist.
        self.assertEqual([s.change for s in res.survivors], ["the number 1 becomes 2"])
        self.assertNotIn("`.fullmatch` becomes `.match`", [s.change for s in res.survivors])

    def test_tests_that_look_at_one_answer_miss_most_changes(self):
        res = run({**FILES, "tests/test_user.py": WEAK})
        self.assertEqual(res.status, "ok", res.note)
        self.assertLess(res.score, 60)
        self.assertIn("`.fullmatch` becomes `.match`", [s.change for s in res.survivors])

    def test_tests_that_fail_on_the_original_prove_nothing(self):
        bad = TESTS.replace('self.assertEqual(call({"name": "alice"}), 200)', 'self.assertEqual(call({"name": "alice"}), 500)')
        res = run({**FILES, "tests/test_user.py": bad})
        self.assertEqual(res.status, "skipped")
        self.assertIn("do not all pass", res.note)

    def test_off_and_missing_pieces_are_skipped_with_a_reason(self):
        self.assertEqual(run(limit=0).note, "mutation check is off")
        self.assertIn("no tests", mut.run_mutation(FILES, CODE, [], 5, python=sys.executable).note)
        self.assertIn("no mutation operator", mut.run_mutation({**FILES, "handlers/user.py": "X = 'a'\n"}, CODE, TEST, 5,
                                                              python=sys.executable).note)

    def test_the_time_budget_leaves_the_rest_out_and_says_so(self):
        ticks = iter([0.0] + [0.0, 0.0, 999.0] + [999.0] * 100)
        res = run(limit=8, budget_s=10, workers=1, clock=lambda: next(ticks))
        self.assertEqual(res.status, "ok")
        self.assertLess(res.run, 8)
        self.assertIn("left out", res.stopped)

    def test_a_mutant_that_hangs_counts_as_caught(self):
        self.assertTrue(mut._caught({"status": "timeout after 1s"}))
        self.assertTrue(mut._caught({"status": "ok", "tests": {"a": "pass", "b": "error"}}))
        self.assertFalse(mut._caught({"status": "ok", "tests": {"a": "pass"}}))

    def test_the_text_for_a_repair_round_names_line_and_change(self):
        res = run()
        text = mut.survivors_text(res)
        self.assertIn("were caught", text)
        self.assertIn(f"handlers/user.py:{res.survivors[0].line}", text)
        self.assertIn("Do not change the code files", text)


class EffortTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("GENERATOR_MUTANTS", None)

    def test_the_numbers_per_effort(self):
        self.assertEqual((resolve("quick").mutants, resolve("quick").strengthen), (0, False))
        self.assertEqual((resolve("standard").mutants, resolve("standard").strengthen), (12, False))
        self.assertEqual((resolve("deep").mutants, resolve("deep").strengthen), (30, True))

    def test_the_environment_replaces_the_default_and_a_knob_wins_over_it(self):
        os.environ["GENERATOR_MUTANTS"] = "5"
        self.assertEqual(resolve("deep").mutants, 5)
        self.assertEqual(resolve("deep", mutants=9).mutants, 9)
        os.environ["GENERATOR_MUTANTS"] = "0"
        self.assertEqual((resolve("deep").mutants, resolve("deep").strengthen), (0, False))
        os.environ["GENERATOR_MUTANTS"] = "junk"
        self.assertEqual(resolve("standard").mutants, 12)

    def test_out_of_range_is_refused(self):
        with self.assertRaises(EffortError):
            resolve("standard", mutants=101)
        with self.assertRaises(EffortError):
            resolve("standard", mutants=-1)


class GateTests(unittest.TestCase):
    def test_a_low_score_blocks_only_when_asked(self):
        import dataclasses
        p = prepare()
        v = dataclasses.replace(p["verify"], mutation_score=40.0)
        self.assertFalse(any("changes made to the code" in r for r in evaluate_gate(p["design"], p["build"], v).reasons))
        res = evaluate_gate(p["design"], p["build"], v, Gate(min_mutation_score=70))
        self.assertTrue(any("caught 40% of the changes" in r for r in res.reasons), res.reasons)
        ok = dataclasses.replace(p["verify"], mutation_score=90.0)
        self.assertFalse(any("changes made" in r for r in evaluate_gate(p["design"], p["build"], ok, Gate(min_mutation_score=70)).reasons))
        none = dataclasses.replace(p["verify"], mutation_score=None)
        self.assertFalse(any("changes made" in r for r in evaluate_gate(p["design"], p["build"], none, Gate(min_mutation_score=70)).reasons))

    def test_the_key_is_parsed_and_checked(self):
        self.assertEqual(parse_gate({"min_mutation_score": 70}).min_mutation_score, 70.0)
        self.assertIsNone(parse_gate({}).min_mutation_score)
        for bad in (101, -1, True, "70"):
            with self.assertRaises(QualityGateError, msg=str(bad)):
                parse_gate({"min_mutation_score": bad})


def _verify_with(*pairs):
    reqs = tuple(RequirementVerdict(rid, "high", "passed", tuple(Evidence("attack", name, st, detail) for name, st, detail in rows))
                 for rid, rows in pairs)
    return VerifyResult(reqs, "passed", False, 0, "ok", 90.0, "", ())


class CandidateTests(unittest.TestCase):
    def test_probes_answered_differently_are_listed(self):
        a = Candidate(0, verify=_verify_with(("R1", [("trailing space", "pass", "answered 400"), ("empty", "pass", "answered 400")])))
        b = Candidate(1, verify=_verify_with(("R1", [("trailing space", "pass", "answered 404"), ("empty", "pass", "answered 400")])))
        rows = disagreements([a, b, Candidate(2, error="x")])
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["requirement"], rows[0]["probe"]), ("R1", "trailing space"))
        self.assertEqual([x["answer"] for x in rows[0]["answers"]], ["answered 400", "answered 404"])

    def test_one_candidate_or_full_agreement_gives_nothing(self):
        a = Candidate(0, verify=_verify_with(("R1", [("empty", "pass", "answered 400")])))
        self.assertEqual(disagreements([a]), [])
        self.assertEqual(disagreements([a, Candidate(1, verify=_verify_with(("R1", [("empty", "pass", "answered 400")])))]), [])


class QuestionTests(unittest.TestCase):
    def gap(self, gid, kind, text, sev="critical"):
        return Gap(gid, kind, sev, text, None)

    def test_each_kind_of_gap_becomes_a_question(self):
        gaps = [self.gap("G1", "missing_input", "the response to invalid input is not given"),
                self.gap("G2", "assumption", 'text says "Called by the public web app." but no requirement covers it (x)', "noted"),
                self.gap("G3", "contradiction", "a is in must_never and in should"),
                self.gap("G4", "secret", "the spec contains 1 api key value(s)"),
                self.gap("G5", "reminder", "domain payments: idempotency?", "noted")]
        rows = questions_for(gaps, [])
        self.assertEqual([r["gap"] for r in rows], ["G1", "G2", "G3", "G4", "G5"])
        self.assertIn("The spec does not say", rows[0]["question"])
        self.assertIn('"Called by the public web app."', rows[1]["question"])
        self.assertIn("disagree", rows[2]["question"])
        self.assertIn("environment variable", rows[3]["question"])
        self.assertIn("add it to the spec", rows[4]["question"])

    def test_the_models_own_answer_is_set_beside_the_question(self):
        gaps = [self.gap("G1", "assumption", "x", "noted"), self.gap("G2", "assumption", "y", "noted")]
        rows = questions_for(gaps, [{"file": "h.py", "line": 7, "text": "G2 public endpoint, no sign-in"}])
        self.assertEqual(rows[0]["assumed"], "")
        self.assertEqual(rows[1]["assumed"], "G2 public endpoint, no sign-in (h.py:7)")


class FeedbackOrderTests(unittest.TestCase):
    def test_critical_problems_come_first(self):
        reqs = (RequirementVerdict("R1", "medium", "failed", ()), RequirementVerdict("R2", "critical", "failed", ()),
                RequirementVerdict("R3", "high", "failed", ()))
        v = VerifyResult(reqs, "failed", False, 0, "ok", 90.0, "", ())
        from generator.pipeline.build import BuildCheck
        text = feedback_text(BuildCheck(files=(), errors=()), v)
        self.assertEqual([line.split()[0] for line in text.splitlines()], ["R2", "R3", "R1"])


def files_answer(tests):
    return json.dumps({"files": {"handlers/__init__.py": "", "handlers/user.py": GOOD,
                                 "tests/__init__.py": "", "tests/test_user.py": tests}})


class PipelineTests(unittest.TestCase):
    def go(self, *answers, **kw):
        stub = Stub(*answers)
        lines = []
        res = run_pipeline(CLEAN_SPEC, chat_fn=stub, today=TODAY, analyzer=None, allow_write=False, text_check=False,
                           log=lines.append, **kw)
        return res, stub, lines

    def test_standard_runs_the_check_and_reports_it(self):
        res, stub, lines = self.go(files_answer(TESTS6), mutants=12)
        self.assertEqual(res.verify.code_verdict, "passed")
        self.assertEqual(res.mutation.status, "ok")
        self.assertEqual(res.verify.mutation_score, res.mutation.score)
        self.assertEqual(len(stub.calls), 1)                     # no strengthening outside deep
        self.assertTrue(any(line.startswith("[Verify]    mutation:") for line in lines), lines)
        d = res.to_dict()
        self.assertEqual(d["mutation"]["score"], res.mutation.score)
        md = render_markdown(res, "spec.yaml")
        self.assertIn("## Mutation check", md)
        self.assertIn("Change not caught", md)
        self.assertTrue(any(n.startswith("mutation:") for n in res.verify.notes))

    def test_quick_and_zero_do_not_run_it(self):
        res, _, _ = self.go(files_answer(TESTS6), mutants=0)
        self.assertIsNone(res.mutation)
        self.assertNotIn("mutation", res.to_dict())
        self.assertIsNone(res.verify.mutation_score)

    def test_deep_asks_once_for_better_tests_and_takes_them_when_the_score_rises(self):
        res, stub, lines = self.go(files_answer(WEAK), files_answer(TESTS6), effort="deep", candidates=1, cove=False, mutants=40)
        self.assertEqual(len(stub.calls), 2, lines)
        self.assertIn("mutation:", stub.calls[1][-1]["content"])
        self.assertIn("Do not change the code files", stub.calls[1][-1]["content"])
        self.assertEqual(res.files["tests/test_user.py"], TESTS6)
        self.assertEqual(res.repair_rounds, 1)
        self.assertTrue(any("tests strengthened" in line for line in lines), lines)
        self.assertEqual(res.verify.code_verdict, "passed")

    def test_the_new_tests_are_not_taken_when_the_score_does_not_rise(self):
        res, stub, lines = self.go(files_answer(WEAK), files_answer(WEAK), effort="deep", candidates=1, cove=False, mutants=40)
        self.assertEqual(res.files["tests/test_user.py"], WEAK)
        self.assertTrue(any("not taken" in line for line in lines), lines)
        self.assertEqual(res.repair_rounds, 1)

    def test_good_tests_are_left_alone(self):
        res, stub, lines = self.go(files_answer(TESTS6), files_answer(WEAK), effort="deep", candidates=1, cove=False, mutants=40)
        self.assertGreaterEqual(res.mutation.score, 90)
        self.assertEqual(len(stub.calls), 1)              # a survivor or two do not buy another model call
        self.assertEqual(res.repair_rounds, 0)

    def test_a_failing_strengthening_round_keeps_the_files(self):
        from generator.llm import LLMError
        res, stub, lines = self.go(files_answer(WEAK), LLMError("down"), effort="deep", candidates=1, cove=False, mutants=40)
        self.assertEqual(res.verify.code_verdict, "passed")
        self.assertTrue(any("strengthening round failed" in line for line in lines), lines)
        self.assertEqual(res.repair_rounds, 0)

    def test_a_code_that_did_not_pass_is_not_mutated(self):
        from tests.test_verify import DOLLAR_BUG
        res, _, _ = self.go(json.dumps({"files": {"handlers/__init__.py": "", "handlers/user.py": DOLLAR_BUG,
                                                  "tests/__init__.py": "", "tests/test_user.py": TESTS6}}),
                            mutants=12, repairs=0)
        self.assertNotEqual(res.verify.code_verdict, "passed")
        self.assertIsNone(res.mutation)

    def test_the_questions_reach_the_result_and_the_report(self):
        res, _, _ = self.go(files_answer(TESTS6), mutants=0)
        d = res.to_dict()
        self.assertIsInstance(d["questions"], list)
        self.assertEqual(d["questions"], [])      # the clean spec has no gaps


if __name__ == "__main__":
    unittest.main()
