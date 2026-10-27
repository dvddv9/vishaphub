import unittest

from tests.helpers import BASE, EXAMPLE, write_spec

from generator.design import design
from generator.spec import load_spec


class DesignTests(unittest.TestCase):
    def test_example_plans_three_files(self):
        res = design(load_spec(EXAMPLE))
        self.assertEqual([(f.path, f.role) for f in res.files], [
            ("handlers/__init__.py", "package"),
            ("handlers/user.py", "code"),
            ("tests/test_user.py", "test"),
        ])

    def test_example_gaps_come_with_the_design(self):
        res = design(load_spec(EXAMPLE))
        self.assertEqual(len(res.critical_gaps), 1)

    def test_code_file_serves_every_requirement(self):
        code = [f for f in design(load_spec(EXAMPLE)).files if f.role == "code"][0]
        self.assertEqual(code.requirements, ("R1", "R2", "R3", "R4", "R5"))
        self.assertEqual(code.library_check, ("flask",))
        self.assertEqual(code.measures, ("validation",))
        self.assertIn("name (query)", code.interface)
        self.assertIn("outputs: 200, 404", code.interface)

    def test_test_file_names_tests_after_requirements(self):
        test = [f for f in design(load_spec(EXAMPLE)).files if f.role == "test"][0]
        self.assertIn("test_r1", test.interface)
        self.assertIn("test_r5", test.interface)
        self.assertEqual(test.requirements, ("R1", "R2", "R3", "R4", "R5"))

    def test_nested_output_gets_a_package_marker_per_folder(self):
        text = BASE + "target: python/flask\nkind: function\noutput: app/api/users.py\n"
        res = design(load_spec(write_spec(text)))
        self.assertEqual([f.path for f in res.files if f.role == "package"],
                         ["app/__init__.py", "app/api/__init__.py"])

    def test_signed_in_caller_adds_auth(self):
        text = BASE + "target: python/flask\nkind: http-endpoint\noutput: h.py\ncaller: signed-in\n"
        code = [f for f in design(load_spec(write_spec(text))).files if f.role == "code"][0]
        self.assertEqual(code.measures[0], "auth")

    def test_rate_limit_from_rule_id(self):
        text = BASE + ("target: python/flask\nkind: function\noutput: h.py\n"
                       "should:\n  - id: rate-limit-10-per-minute\n    text: at most 10 calls a minute\n")
        code = [f for f in design(load_spec(write_spec(text))).files if f.role == "code"][0]
        self.assertIn("rate_limit", code.measures)

    def test_no_output_no_files(self):
        res = design(load_spec(write_spec(BASE)))
        self.assertEqual(res.files, ())
        self.assertTrue(any("output" in g.text for g in res.critical_gaps))

    def test_non_python_target_plans_code_only_and_says_so(self):
        text = BASE + "target: terraform\nkind: module\noutput: main.tf\n"
        res = design(load_spec(write_spec(text)))
        self.assertEqual([f.role for f in res.files], ["code"])
        self.assertTrue(any("not planned yet" in g.text for g in res.gaps))
        self.assertEqual(res.gaps[-1].id, f"G{len(res.gaps)}")

    def test_to_dict(self):
        d = design(load_spec(EXAMPLE)).to_dict()
        self.assertEqual(len(d["files"]), 3)
        self.assertEqual(len(d["gaps"]), 1)


if __name__ == "__main__":
    unittest.main()
