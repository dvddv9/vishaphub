import unittest

from tests.helpers import BASE, EXAMPLE, write_spec

from generator.pipeline.intake import intake


class IntakeTests(unittest.TestCase):
    def test_example_gives_five_requirements_in_order(self):
        res = intake(EXAMPLE)
        self.assertEqual([r.id for r in res.requirements],
                         ["R1", "R2", "R3", "R4", "R5"])

    def test_example_priorities(self):
        res = intake(EXAMPLE)
        self.assertEqual([r.priority for r in res.requirements],
                         ["high", "high", "high", "critical", "critical"])

    def test_example_verify_methods(self):
        res = intake(EXAMPLE)
        self.assertEqual(res.requirements[0].verify, ("rule", "test"))
        self.assertEqual(res.requirements[1].verify, ("test",))
        self.assertEqual(res.requirements[3].verify, ("rule", "test"))

    def test_source_line_points_at_the_right_line(self):
        res = intake(EXAMPLE)
        lines = EXAMPLE.read_text(encoding="utf-8").splitlines()
        expected = [
            ("inputs", "name: name"),
            ("outputs", "status: 200"),
            ("outputs", "status: 404"),
            ("must_never", "id: sql-from-input"),
            ("must_never", "id: log-raw-input"),
        ]
        for req, (field, needle) in zip(res.requirements, expected):
            self.assertEqual(req.source.field, field)
            self.assertIn(needle, lines[req.source.line - 1],
                          f"{req.id} points at line {req.source.line}")

    def test_input_text_includes_rule(self):
        res = intake(EXAMPLE)
        self.assertEqual(res.requirements[0].text,
                         "Input name (query): 1-64 letters and digits")

    def test_output_text(self):
        res = intake(EXAMPLE)
        self.assertEqual(res.requirements[1].text,
                         "Status 200 returns json: id, name only")
        self.assertEqual(res.requirements[2].text,
                         "Status 404 when no such user")

    def test_must_never_text_is_the_spec_text(self):
        res = intake(EXAMPLE)
        self.assertEqual(res.requirements[3].text,
                         "SQL is never built from the input")

    def test_order_across_all_lists(self):
        text = BASE + (
            "should:\n"
            "  - id: audit-log\n"
            "    text: write an audit line per call\n"
            "may:\n"
            "  - id: metrics\n"
            "    text: count calls\n"
        )
        res = intake(write_spec(text))
        self.assertEqual([r.source.field for r in res.requirements],
                         ["inputs", "outputs", "must_never", "should", "may"])
        self.assertEqual(res.requirements[-2].priority, "high")
        self.assertEqual(res.requirements[-1].priority, "medium")

    def test_result_carries_spec_hash_and_date(self):
        p = write_spec(BASE)
        res = intake(p)
        import hashlib
        self.assertEqual(res.spec_sha256, hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertEqual(res.updated.isoformat(), "2026-10-27")

    def test_to_dict_is_plain_data(self):
        d = intake(EXAMPLE).to_dict()
        self.assertEqual(d["updated"], "2026-10-27")
        self.assertEqual(d["requirements"][0]["source"]["field"], "inputs")
        self.assertIsInstance(d["requirements"][0]["verify"], list)


if __name__ == "__main__":
    unittest.main()
