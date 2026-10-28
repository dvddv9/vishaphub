import unittest

from tests.helpers import BASE, EXAMPLE, write_spec

from generator.tools.gaps import find_gaps
from generator.tools.spec import load_spec

FULL = BASE + (
    "target: python/flask\n"
    "kind: http-endpoint\n"
    "output: handlers/user.py\n"
    "caller: public\n"
    "profile: owasp-asvs-2\n"
    "check: analyzer\n"
)


def gaps_for(text):
    return find_gaps(load_spec(write_spec(text)))


def kinds(gaps):
    return [(g.type, g.severity) for g in gaps]


class GapTests(unittest.TestCase):
    def test_example_has_one_critical_gap(self):
        gaps = find_gaps(load_spec(EXAMPLE))
        self.assertEqual(kinds(gaps), [("missing_input", "critical")])
        self.assertIn("invalid input", gaps[0].text)
        self.assertEqual([g.id for g in gaps], ["G1"])

    def test_example_without_caller_has_two(self):
        text = EXAMPLE.read_text(encoding="utf-8").replace("caller: public\n", "")
        gaps = gaps_for(text)
        self.assertEqual([g.severity for g in gaps], ["critical", "critical"])
        self.assertIn("who calls", gaps[0].text)

    def test_complete_spec_has_one_gap_for_invalid_input(self):
        gaps = gaps_for(FULL)
        self.assertEqual(len(gaps), 1)
        self.assertIn("invalid input", gaps[0].text)

    def test_400_output_closes_the_invalid_input_gap(self):
        text = FULL + "" 
        text = text.replace(
            '    body: "json: id, name only"\n',
            '    body: "json: id, name only"\n  - status: 400\n    when: "name breaks the rule"\n')
        self.assertEqual(gaps_for(text), ())

    def test_missing_target_kind_output(self):
        gaps = gaps_for(BASE)
        texts = [g.text for g in gaps if g.type == "missing_input"]
        for key in ("target", "kind", "output"):
            self.assertTrue(any(t.startswith(key) for t in texts), key)

    def test_caller_gap_points_at_kind(self):
        text = FULL.replace("caller: public\n", "")
        gaps = gaps_for(text)
        caller = [g for g in gaps if "who calls" in g.text][0]
        self.assertEqual(caller.source.field, "kind")
        lines = text.splitlines()
        self.assertIn("kind:", lines[caller.source.line - 1])

    def test_no_caller_gap_for_a_function(self):
        text = FULL.replace("kind: http-endpoint", "kind: function").replace("caller: public\n", "")
        self.assertFalse(any("who calls" in g.text for g in gaps_for(text)))

    def test_input_without_rule_is_an_assumption(self):
        text = FULL.replace('    rule: "1-64 letters and digits"\n', "")
        gaps = gaps_for(text)
        self.assertEqual(kinds(gaps), [("assumption", "noted")])
        self.assertEqual(gaps[0].source.field, "inputs")

    def test_input_without_rule_with_validate_inputs_is_missing(self):
        text = FULL.replace('    rule: "1-64 letters and digits"\n', "") + "constraints: [validate-inputs]\n"
        gaps = gaps_for(text)
        self.assertEqual(kinds(gaps), [("missing_input", "critical")])

    def test_profile_and_check_defaults_are_assumptions(self):
        text = FULL.replace("profile: owasp-asvs-2\n", "").replace("check: analyzer\n", "")
        gaps = [g for g in gaps_for(text) if g.type == "assumption"]
        self.assertEqual(len(gaps), 2)

    def test_asvs_with_check_none_is_a_contradiction(self):
        text = FULL.replace("check: analyzer", "check: none")
        contra = [g for g in gaps_for(text) if g.type == "contradiction"]
        self.assertEqual(len(contra), 1)
        self.assertEqual(contra[0].severity, "critical")
        self.assertEqual(contra[0].source.field, "check")

    def test_same_text_in_must_never_and_should(self):
        text = FULL + "should:\n  - id: sql-again\n    text: \"SQL is never built from the input\"\n"
        contra = [g for g in gaps_for(text) if g.type == "contradiction"]
        self.assertEqual(len(contra), 1)
        self.assertEqual(contra[0].source.field, "should")

    def test_to_dict(self):
        d = find_gaps(load_spec(EXAMPLE))[0].to_dict()
        self.assertEqual(d["type"], "missing_input")
        self.assertEqual(d["source"]["field"], "outputs")


if __name__ == "__main__":
    unittest.main()
