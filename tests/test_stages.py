import json
import tempfile
import time
import unittest
from pathlib import Path

from tests import helpers  # noqa: F401
from tests.test_deliver import CLEAN_SPEC
from tests.test_pipeline import Stub, answer
from tests.test_verify import DOLLAR_BUG, GOOD, TODAY

from generator.llm._observe import observe_llm_result
from generator.pipeline.cost import estimate_cost, sum_stage_costs
from generator.pipeline.orchestrator import run_pipeline
from generator.pipeline.stages import BY_KEY, STAGES, StageClock, parse_json_response
from generator.storage.history import load_history


class ParseTests(unittest.TestCase):
    def test_plain_fenced_and_bad(self):
        self.assertEqual(parse_json_response('{"a": 1}'), {"a": 1})
        self.assertEqual(parse_json_response('```json\n{"a": 1}\n```'), {"a": 1})
        with self.assertRaises(ValueError):
            parse_json_response("[1]")
        with self.assertRaises(ValueError):
            parse_json_response('{"a": ')          # cut off: not repaired on purpose


class ClockTests(unittest.TestCase):
    def test_stage_sums_runs_and_usage(self):
        clock = StageClock()
        for _ in range(2):
            with clock.stage("build"):
                observe_llm_result([{"content": "q"}], "a", 10, 5)
                time.sleep(0.001)
        rec = clock.records()[0]
        self.assertEqual((rec["key"], rec["runs"], rec["llm_calls"], rec["tokens_in"], rec["tokens_out"]),
                         ("build", 2, 2, 20, 10))
        self.assertGreater(rec["duration_s"], 0)

    def test_failure_is_recorded_and_raised(self):
        clock = StageClock()
        with self.assertRaises(RuntimeError), clock.stage("verify"):
            raise RuntimeError("boom")
        rec = clock.records()[0]
        self.assertFalse(rec["ok"])
        self.assertIn("boom", rec["error"])

    def test_registry(self):
        self.assertEqual([s.key for s in STAGES], ["intake", "design", "build", "verify", "deliver"])
        self.assertEqual(BY_KEY["build"].number, 3)

    def test_cost_uses_only_given_prices(self):
        self.assertEqual(estimate_cost(1000, 1000, (0.0, 0.0)), 0.0)
        self.assertEqual(estimate_cost(1_000_000, 500_000, (3.0, 15.0)), 10.5)
        self.assertEqual(sum_stage_costs([{"cost_usd": 1.5}, {"cost_usd": 2}, "junk"]), 3.5)


class PipelineRecordsTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.out = Path(self._t.name) / "out"

    def run_it(self, stub, **kw):
        return run_pipeline(CLEAN_SPEC, out_dir=self.out, chat_fn=stub, today=TODAY, analyzer=None, **kw)

    def test_every_stage_is_recorded_in_order(self):
        res = self.run_it(Stub(answer(GOOD)))
        self.assertEqual([s["key"] for s in res.stages], ["intake", "design", "build", "verify", "deliver"])
        self.assertTrue(all(s["ok"] for s in res.stages))

    def test_stand_in_model_calls_are_counted(self):
        res = self.run_it(Stub(answer(GOOD)))
        by = {s["key"]: s for s in res.stages}
        self.assertEqual(by["design"]["llm_calls"], 1)       # the text check
        self.assertEqual(by["build"]["llm_calls"], 1)
        self.assertEqual(res.usage["llm_calls"], 2)

    def test_repair_round_adds_to_build(self):
        res = self.run_it(Stub(answer(DOLLAR_BUG), answer(GOOD)))
        build = next(s for s in res.stages if s["key"] == "build")
        self.assertEqual((build["runs"], build["llm_calls"]), (2, 2))
        self.assertGreaterEqual(next(s for s in res.stages if s["key"] == "verify")["runs"], 2)

    def test_no_llm_stops_after_design_and_has_no_calls(self):
        res = run_pipeline(CLEAN_SPEC, no_llm=True, today=TODAY)
        self.assertEqual([s["key"] for s in res.stages], ["intake", "design"])
        self.assertEqual(res.usage["llm_calls"], 0)

    def test_result_dict_carries_stages_usage_provenance(self):
        d = self.run_it(Stub(answer(GOOD))).to_dict()
        json.dumps(d)
        self.assertEqual(len(d["stages"]), 5)
        self.assertIn("usage", d)
        self.assertEqual(d["provenance"]["spec"]["sha256"], d["spec"]["sha256"])
        self.assertEqual(set(d["provenance"]["prompts"]), {"00_rules", "02_design_textcheck", "03_build",
                                                           "03_build_repair", "04_verify_cove"})

    def test_trace_has_provenance_and_no_timings(self):
        self.run_it(Stub(answer(GOOD)))
        trace = json.loads((self.out / ".vishap/user.trace.json").read_text())
        self.assertIn("provenance", trace)
        self.assertNotIn("duration_s", json.dumps(trace))
        self.assertNotIn("key", trace["provenance"].get("model") or {})

    def test_history_gets_one_entry_per_written_run(self):
        res = self.run_it(Stub(answer(GOOD)))
        entries = load_history(self.out)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["run_id"], res.deliver.run_id)
        self.assertEqual(entries[0]["verdict"], "passed")
        self.assertEqual(entries[0]["usage"]["llm_calls"], 2)

    def test_dry_run_and_api_mode_leave_no_history(self):
        self.run_it(Stub(answer(GOOD)), dry_run=True)
        self.assertEqual(load_history(self.out), [])
        run_pipeline(CLEAN_SPEC, chat_fn=Stub(answer(GOOD)), today=TODAY, analyzer=None, allow_write=False)
        self.assertFalse(self.out.exists())

    def test_a_secret_in_the_spec_does_not_reach_the_model(self):
        text = CLEAN_SPEC.read_text(encoding="utf-8").replace(
            "text: |", "text: |\n  Use the key sk-abcdefghijklmnopqrstuvwx for the lookup.", 1)
        spec = Path(self._t.name) / "spec.yaml"
        spec.write_text(text, encoding="utf-8")
        stub = Stub(answer(GOOD))
        res = run_pipeline(spec, out_dir=self.out, chat_fn=stub, today=TODAY, analyzer=None)
        seen = json.dumps(stub.calls + stub.text_calls)
        self.assertNotIn("sk-abcdefghijkl", seen)
        self.assertEqual(res.provenance["redaction"], {"api-key": 1})


if __name__ == "__main__":
    unittest.main()
