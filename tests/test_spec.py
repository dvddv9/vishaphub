import hashlib
import unittest

from tests.helpers import BASE, EXAMPLE, write_spec

from generator.spec import SpecError, load_spec


class LoadSpecTests(unittest.TestCase):
    def test_example_loads(self):
        spec = load_spec(EXAMPLE)
        self.assertEqual(spec.version, 1)
        self.assertEqual(spec.updated.isoformat(), "2026-10-27")
        self.assertEqual(len(spec.items["inputs"]), 1)
        self.assertEqual(len(spec.items["outputs"]), 2)
        self.assertEqual(len(spec.items["must_never"]), 2)

    def test_sha256_is_of_the_file_bytes(self):
        p = write_spec(BASE)
        spec = load_spec(p)
        self.assertEqual(spec.sha256, hashlib.sha256(p.read_bytes()).hexdigest())

    def test_base_spec_loads(self):
        self.assertEqual(len(load_spec(write_spec(BASE)).items["must_never"]), 1)

    def assert_error(self, text: str, field: str, line_expected=...):
        with self.assertRaises(SpecError) as cm:
            load_spec(write_spec(text))
        err = cm.exception
        self.assertEqual(err.field, field, str(err))
        if line_expected is not ...:
            self.assertEqual(err.line, line_expected, str(err))
        return err

    def test_missing_version(self):
        self.assert_error(BASE.replace("version: 1\n", ""), "version")

    def test_wrong_version(self):
        self.assert_error(BASE.replace("version: 1", "version: 2"), "version", 1)

    def test_updated_must_be_iso_date(self):
        self.assert_error(BASE.replace("2026-10-27", "27.10.2026"), "updated")

    def test_updated_datetime_rejected(self):
        self.assert_error(BASE.replace("2026-10-27", "2026-10-27T10:00:00"), "updated")

    def test_unknown_top_level_key_names_line(self):
        text = BASE + "mustnever:\n  - id: x\n    text: y\n"
        err = self.assert_error(text, "mustnever")
        self.assertIsNotNone(err.line)

    def test_unknown_key_inside_item(self):
        text = BASE.replace('text: "SQL is never built from the input"',
                            'text: "SQL is never built from the input"\n    ids: 1')
        self.assert_error(text, "must_never")

    def test_duplicate_top_level_key(self):
        text = BASE + "text: again\n"
        err = self.assert_error(text, "text")
        self.assertIn("duplicate", err.message)

    def test_duplicate_rule_id_across_lists(self):
        text = BASE + "should:\n  - id: sql-from-input\n    text: other\n"
        err = self.assert_error(text, "should")
        self.assertIn("duplicate id", err.message)

    def test_status_out_of_range(self):
        self.assert_error(BASE.replace("status: 200", "status: 999"), "outputs")

    def test_output_needs_body_or_when(self):
        text = BASE.replace('    body: "json: id, name only"\n', "")
        self.assert_error(text, "outputs")

    def test_input_bad_location(self):
        self.assert_error(BASE.replace("in: query", "in: cookie"), "inputs")

    def test_must_never_as_string_rejected(self):
        text = BASE.replace(
            "must_never:\n  - id: sql-from-input\n    text: \"SQL is never built from the input\"\n",
            "must_never: SQL is never built\n")
        self.assert_error(text, "must_never")

    def test_empty_text(self):
        self.assert_error(BASE.replace("  Read one user.", "  "), "text")

    def test_no_requirements(self):
        text = "version: 1\nupdated: 2026-10-27\ntext: x\n"
        err = self.assert_error(text, "file")
        self.assertIn("no requirements", err.message)

    def test_invalid_yaml_reports_line(self):
        text = BASE + "  bad: [unclosed\n"
        with self.assertRaises(SpecError) as cm:
            load_spec(write_spec(text))
        self.assertEqual(cm.exception.field, "file")
        self.assertIsNotNone(cm.exception.line)

    def test_top_level_list_rejected(self):
        self.assert_error("- a\n- b\n", "file", 1)

    def test_unknown_constraint(self):
        text = BASE + "constraints: [do-everything]\n"
        self.assert_error(text, "constraints")

    def test_output_path_must_stay_inside(self):
        for bad in ("../x.py", "a/../../x.py", "/etc/x.py", "C:/x.py", "a//x.py", "./x.py"):
            with self.subTest(bad=bad):
                self.assert_error(BASE + f"output: {bad}\n", "output")

    def test_output_path_backslash_rejected(self):
        self.assert_error(BASE + "output: 'a\\x.py'\n", "output")

    def test_good_output_path(self):
        spec = load_spec(write_spec(BASE + "output: handlers/user.py\n"))
        self.assertEqual(spec.data["output"], "handlers/user.py")

    def test_caller_values(self):
        load_spec(write_spec(BASE + "caller: signed-in\n"))
        self.assert_error(BASE + "caller: anyone\n", "caller")

    def test_route(self):
        load_spec(write_spec(BASE + "route: GET /user\n"))
        load_spec(write_spec(BASE + "route: POST /users/{id}\n"))
        for bad in ("user", "GET user", "FETCH /user", "GET /user now"):
            with self.subTest(bad=bad):
                self.assert_error(BASE + f"route: {bad}\n", "route")

    def test_key_lines(self):
        spec = load_spec(write_spec(BASE))
        self.assertEqual(spec.key_lines["version"], 1)
        self.assertEqual(spec.key_lines["inputs"], 5)


if __name__ == "__main__":
    unittest.main()
