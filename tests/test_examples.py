import datetime as dt
import tempfile
import unittest
from pathlib import Path

import tests.helpers  # noqa: F401  (puts src on the path)

from generator.pipeline.design import design
from generator.tools.examples import EXAMPLES, examples
from generator.pipeline.intake import requirements_from
from generator.tools.spec import load_spec


class ExampleSpecTests(unittest.TestCase):
    def load(self, ex):
        d = tempfile.mkdtemp(prefix="ex-")
        p = Path(d) / "spec.yaml"
        p.write_text(ex["spec"], encoding="utf-8")
        return load_spec(p)

    def test_every_example_loads_and_designs(self):
        for ex in examples():
            with self.subTest(ex["id"]):
                spec = self.load(ex)
                reqs = requirements_from(spec)
                self.assertGreaterEqual(len(reqs), 4)
                self.assertTrue(design(spec, reqs).files)

    def test_only_the_gap_example_has_a_critical_gap(self):
        gaps = {}
        for ex in examples():
            spec = self.load(ex)
            gaps[ex["id"]] = [g.id for g in design(spec, requirements_from(spec)).critical_gaps]
        self.assertEqual(gaps["user-lookup"], [])
        self.assertEqual(gaps["with-a-gap"], ["G1"])
        self.assertEqual(gaps["order-signed-in"], [])

    def test_today_is_filled_in_and_the_example_is_fresh(self):
        day = dt.date(2026, 10, 28)
        for ex in examples(day):
            self.assertIn("updated: 2026-10-28", ex["spec"])
            self.assertNotIn("{today}", ex["spec"])
            self.assertEqual(self.load(ex).updated, day)

    def test_ids_are_unique_and_titled(self):
        ids = [e["id"] for e in EXAMPLES]
        self.assertEqual(len(ids), len(set(ids)))
        for e in EXAMPLES:
            self.assertTrue(e["title"] and e["description"])


if __name__ == "__main__":
    unittest.main()
