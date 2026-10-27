import subprocess
import unittest
from unittest import mock

from tests.helpers import EXAMPLE

from generator.build import check_build
from generator.design import design
from generator.intake import requirements_from
from generator.spec import load_spec

CODE = '''\
import re

from flask import Flask, abort, jsonify, request

app = Flask(__name__)
NAME = re.compile(r"[A-Za-z0-9]{1,64}")


@app.get("/user")
def get_user():
    name = request.args.get("name", "")
    if not NAME.fullmatch(name):
        abort(400)
    return jsonify(id=1, name=name)
'''

TESTS = '''\
import unittest


class UserTests(unittest.TestCase):
    def test_r1_bad_name(self):
        pass

    def test_r2(self):
        pass

    def test_r3_unknown(self):
        pass

    def test_r4_quote(self):
        pass

    def test_r5(self):
        pass
'''


def setup():
    spec = load_spec(EXAMPLE)
    reqs = requirements_from(spec)
    return design(spec, reqs), reqs


def good_files():
    return {
        "handlers/__init__.py": "",
        "handlers/user.py": CODE,
        "tests/__init__.py": "",
        "tests/test_user.py": TESTS,
    }


@mock.patch("generator.build.shutil.which", return_value=None)
class BuildCheckTests(unittest.TestCase):
    def test_good_files_pass(self, _which):
        d, reqs = setup()
        res = check_build(d, reqs, good_files())
        self.assertTrue(res.ok, res.to_dict())
        test = [f for f in res.files if f.role == "test"][0]
        self.assertEqual(len(test.tests_found), 5)

    def test_ruff_missing_is_skipped_not_passed(self, _which):
        d, reqs = setup()
        res = check_build(d, reqs, good_files())
        self.assertEqual({f.lint for f in res.files}, {"skipped"})
        self.assertIn("not installed", res.files[0].lint_note)

    def test_missing_test_for_a_requirement(self, _which):
        d, reqs = setup()
        files = good_files()
        files["tests/test_user.py"] = TESTS.replace("def test_r3_unknown", "def check_r3")
        res = check_build(d, reqs, files)
        self.assertFalse(res.ok)
        test = [f for f in res.files if f.role == "test"][0]
        self.assertEqual(test.errors, ("no test for R3 (expected test_r3)",))

    def test_r10_does_not_count_for_r1(self, _which):
        d, reqs = setup()
        files = good_files()
        files["tests/test_user.py"] = TESTS.replace("def test_r1_bad_name", "def test_r10_bad_name")
        test = [f for f in check_build(d, reqs, files).files if f.role == "test"][0]
        self.assertIn("no test for R1 (expected test_r1)", test.errors)
        self.assertIn("a test names R10, which is not a requirement", test.errors)

    def test_name_in_a_comment_does_not_count(self, _which):
        d, reqs = setup()
        files = good_files()
        files["tests/test_user.py"] = TESTS.replace(
            "    def test_r5(self):\n        pass\n", "    # test_r5 later\n")
        test = [f for f in check_build(d, reqs, files).files if f.role == "test"][0]
        self.assertIn("no test for R5 (expected test_r5)", test.errors)

    def test_syntax_error_reports_line_and_skips_lint(self, _which):
        d, reqs = setup()
        files = good_files()
        files["handlers/user.py"] = CODE.replace("def get_user():", "def get_user(:")
        code = [f for f in check_build(d, reqs, files).files if f.role == "code"][0]
        self.assertEqual(code.syntax, "error")
        self.assertIn("line 10", code.errors[0])
        self.assertEqual(code.lint, "skipped")

    def test_all_problems_are_collected(self, _which):
        d, reqs = setup()
        files = good_files()
        files["handlers/user.py"] = "def (:\n"
        files["tests/test_user.py"] = "def test_r2():\n    pass\n"
        res = check_build(d, reqs, files)
        bad = [f for f in res.files if f.errors]
        self.assertEqual(len(bad), 2)

    def test_missing_and_extra_files(self, _which):
        d, reqs = setup()
        files = good_files()
        del files["handlers/__init__.py"]
        files["../evil.py"] = ""
        res = check_build(d, reqs, files)
        self.assertIn("missing file handlers/__init__.py", res.errors)
        self.assertIn("file ../evil.py is not in the plan", res.errors)
        self.assertFalse(res.ok)

    def test_async_and_module_level_tests_count(self, _which):
        d, reqs = setup()
        files = good_files()
        files["tests/test_user.py"] = (
            "def test_r1(): pass\n"
            "async def test_r2_async(): pass\n"
            "def test_r3(): pass\n"
            "def test_r4(): pass\n"
            "def test_r5(): pass\n")
        self.assertTrue(check_build(d, reqs, files).ok)


class RuffTests(unittest.TestCase):
    def test_ruff_fail_is_an_error(self):
        d, reqs = setup()
        failed = subprocess.CompletedProcess([], 1, stdout="F401 unused import", stderr="")
        with mock.patch("generator.build.shutil.which", return_value="/usr/bin/ruff"), \
             mock.patch("generator.build.subprocess.run", return_value=failed):
            res = check_build(d, reqs, good_files())
        code = [f for f in res.files if f.role == "code"][0]
        self.assertEqual(code.lint, "fail")
        self.assertIn("F401", code.lint_note)
        self.assertIn("ruff found problems", code.errors)

    def test_ruff_pass(self):
        d, reqs = setup()
        ok = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with mock.patch("generator.build.shutil.which", return_value="/usr/bin/ruff"), \
             mock.patch("generator.build.subprocess.run", return_value=ok):
            res = check_build(d, reqs, good_files())
        self.assertTrue(res.ok)
        self.assertEqual({f.lint for f in res.files}, {"pass"})


if __name__ == "__main__":
    unittest.main()
