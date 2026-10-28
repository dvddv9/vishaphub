import dataclasses
import tempfile
import unittest
from pathlib import Path

from tests.helpers import EXAMPLE
from tests.test_deliver import prepare

from generator.pipeline.verdict import apply_build_errors, compute_code_verdict, compute_spec_verdict
from generator.tools.baseline import compute_fingerprint, filter_new, load_baseline, save_baseline
from generator.tools.quality_gate import (CONFIG_NAME, Gate, QualityGateError, evaluate_gate,
                                          load_quality_gate, parse_gate)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dir = Path(self._t.name)

    def write(self, text):
        (self.dir / CONFIG_NAME).write_text(text, encoding="utf-8")

    def test_no_file_gives_the_defaults(self):
        g = load_quality_gate(self.dir)
        self.assertEqual((g.coverage_min, g.stale_days, g.fail_on), (80.0, 90, ("critical", "high")))

    def test_file_changes_the_thresholds(self):
        self.write("quality_gate:\n  coverage_min: 60\n  stale_days: 30\n  fail_on: [critical]\n")
        g = load_quality_gate(self.dir)
        self.assertEqual((g.coverage_min, g.stale_days, g.fail_on), (60.0, 30, ("critical",)))

    def test_unknown_key_is_an_error(self):
        self.write("quality_gate:\n  coverge_min: 60\n")
        with self.assertRaises(QualityGateError) as cm:
            load_quality_gate(self.dir)
        self.assertIn("coverge_min", str(cm.exception))
        self.assertIn("coverage_min", str(cm.exception))

    def test_bad_values_are_errors(self):
        for text in ("quality_gate:\n  coverage_min: 120\n", "quality_gate:\n  fail_on: [low]\n",
                     "quality_gate:\n  stale_days: -1\n", "quality_gate:\n  require_coverage: yes please\n",
                     "quality_gate: 5\n", "- a list\n"):
            self.write(text)
            with self.assertRaises(QualityGateError, msg=text):
                load_quality_gate(self.dir)

    def test_the_first_folder_with_a_file_wins(self):
        other = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(other, ignore_errors=True))
        (other / CONFIG_NAME).write_text("quality_gate:\n  stale_days: 5\n", encoding="utf-8")
        self.write("quality_gate:\n  stale_days: 7\n")
        self.assertEqual(load_quality_gate(self.dir, other).stale_days, 7)
        self.assertEqual(load_quality_gate(Path(tempfile.gettempdir()) / "nope-x", other).stale_days, 5)

    def test_no_folder_means_defaults_and_reads_nothing(self):
        self.assertEqual(load_quality_gate(), Gate())


class EvaluateTests(unittest.TestCase):
    def test_a_looser_threshold_lets_low_coverage_through(self):
        p = prepare()
        v = dataclasses.replace(p["verify"], coverage_status="below", coverage_percent=61.0)
        self.assertTrue(evaluate_gate(p["design"], p["build"], v).blocked)
        v = dataclasses.replace(p["verify"], coverage_status="ok", coverage_percent=61.0)
        self.assertFalse(evaluate_gate(p["design"], p["build"], v, Gate(coverage_min=60)).blocked)

    def test_fail_on_critical_only_ignores_a_high_requirement(self):
        from tests.test_verify import DOLLAR_BUG
        p = prepare(DOLLAR_BUG)
        self.assertTrue(evaluate_gate(p["design"], p["build"], p["verify"]).blocked)
        g = evaluate_gate(p["design"], p["build"], p["verify"], Gate(fail_on=("critical",)))
        self.assertFalse(any(r.startswith("R1 (high)") for r in g.reasons))

    def test_stale_days_come_from_the_gate(self):
        p = prepare()
        v = dataclasses.replace(p["verify"], spec_age_days=40)
        self.assertFalse(evaluate_gate(p["design"], p["build"], v).blocked)
        self.assertTrue(evaluate_gate(p["design"], p["build"], v, Gate(stale_days=30)).blocked)

    def test_max_critical_gaps(self):
        p = prepare(spec_path=EXAMPLE)
        self.assertTrue(evaluate_gate(p["design"], p["build"], p["verify"]).blocked)
        g = evaluate_gate(p["design"], p["build"], p["verify"], Gate(max_critical_gaps=1))
        self.assertFalse(any("critical gap" in r for r in g.reasons))

    def test_analyzer_errors_can_be_switched_off(self):
        from generator.tools.analyzer import AnalyzerResult
        p = prepare()
        bad = AnalyzerResult(status="failed", note="x")
        v = dataclasses.replace(p["verify"], analyzer=bad)
        self.assertTrue(evaluate_gate(p["design"], p["build"], v).blocked)
        self.assertFalse(evaluate_gate(p["design"], p["build"], v, Gate(fail_on_analyzer=False)).blocked)


class BaselineTests(unittest.TestCase):
    def test_an_accepted_gap_does_not_block_but_is_reported(self):
        p = prepare(spec_path=EXAMPLE)
        gaps = p["design"].critical_gaps
        self.assertEqual(len(gaps), 1)
        gate = Gate(accepted_gaps=frozenset({compute_fingerprint(gaps[0])}))
        res = evaluate_gate(p["design"], p["build"], p["verify"], gate)
        self.assertFalse(any("critical gap" in r for r in res.reasons))
        self.assertEqual(len(res.accepted), 1)
        self.assertIn("G1", res.accepted[0])

    def test_fingerprint_ignores_the_number_and_the_spacing(self):
        p = prepare(spec_path=EXAMPLE)
        g = p["design"].critical_gaps[0]
        h = dataclasses.replace(g, id="G9", text="  " + g.text.upper().replace(" ", "   "))
        self.assertEqual(compute_fingerprint(g), compute_fingerprint(h))

    def test_save_load_filter(self):
        p = prepare(spec_path=EXAMPLE)
        gaps = list(p["design"].gaps)
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / ".vishap" / "baseline.json"
            prints = save_baseline(gaps, path)
            accepted = load_baseline(path)
        self.assertEqual(set(prints), set(accepted))
        new, old = filter_new(gaps, accepted)
        self.assertEqual((new, len(old)), ([], len(gaps)))

    def test_missing_or_broken_baseline_accepts_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(load_baseline(Path(t) / "none.json"), frozenset())
            bad = Path(t) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            self.assertEqual(load_baseline(bad), frozenset())

    def test_the_default_baseline_is_found_next_to_the_config(self):
        p = prepare(spec_path=EXAMPLE)
        with tempfile.TemporaryDirectory() as t:
            save_baseline(p["design"].critical_gaps, Path(t) / ".vishap" / "baseline.json")
            self.assertEqual(len(load_quality_gate(t).accepted_gaps), 1)
            self.assertEqual(len(parse_gate({}, Path(t)).accepted_gaps), 1)


class VerdictTests(unittest.TestCase):
    def test_spec_verdict(self):
        self.assertEqual(compute_spec_verdict(91), (True, 91))
        self.assertEqual(compute_spec_verdict(90), (False, 90))
        self.assertEqual(compute_spec_verdict(10, stale_days=5), (True, 10))

    def test_code_verdict(self):
        p = prepare()
        vs = p["verify"].requirements
        self.assertEqual(compute_code_verdict(vs, "ok", []), "passed")
        self.assertEqual(compute_code_verdict(vs, "below", []), "needs_verification")
        self.assertEqual(compute_code_verdict(vs, "ok", ["x"]), "needs_verification")
        self.assertEqual(compute_code_verdict(vs, "ok", [], analyzer_failed=True), "failed")

    def test_build_errors_downgrade_a_pass_only(self):
        p = prepare()
        self.assertEqual(p["verify"].code_verdict, "passed")
        v = apply_build_errors(p["verify"], ["tests/test_user.py: a test names R6"])
        self.assertEqual(v.code_verdict, "needs_verification")
        self.assertIn("R6", v.notes[-1])
        self.assertIs(apply_build_errors(p["verify"], []), p["verify"])
        failed = dataclasses.replace(p["verify"], code_verdict="failed")
        self.assertEqual(apply_build_errors(failed, ["x"]).code_verdict, "failed")


if __name__ == "__main__":
    unittest.main()
