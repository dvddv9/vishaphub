import ast
import datetime as dt
import importlib.util
import os
import unittest
from unittest import mock

from tests.helpers import EXAMPLE

from generator.analyzer import AnalyzerResult
from generator.design import design
from generator.intake import requirements_from
from generator.spec import load_spec
from generator.verify import (input_cases, log_findings, parse_rule,
                              sql_findings, verify)

# A plain WSGI app, so these tests run without Flask installed.
GOOD = '''\
import re
from urllib.parse import parse_qs

NAME = re.compile(r"[A-Za-z0-9]{1,64}")
USERS = {"alice": 1}


def _send(start_response, status, body):
    start_response(status, [("Content-Type", "application/json")])
    return [body.encode()]


def app(environ, start_response):
    qs = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    name = qs.get("name", [None])[0]
    if name is None or not NAME.fullmatch(name):
        return _send(start_response, "400 Bad Request", '{"error": "invalid name"}')
    if name not in USERS:
        return _send(start_response, "404 Not Found", '{"error": "not found"}')
    return _send(start_response, "200 OK", '{"id": 1, "name": "alice"}')
'''

# The bug from the first real run: $ matches before a final newline.
DOLLAR_BUG = GOOD.replace('re.compile(r"[A-Za-z0-9]{1,64}")', 're.compile(r"^[A-Za-z0-9]{1,64}$")') \
                 .replace("NAME.fullmatch(name)", "NAME.match(name)")

LOGS_INPUT = GOOD.replace("import re\n", "import logging\nimport re\n").replace(
    "    if name not in USERS:\n",
    "    logging.getLogger(__name__).info('lookup %s', name)\n    if name not in USERS:\n")

SQL_FSTRING = GOOD + '''

def find(conn, name):
    return conn.execute(f"SELECT id FROM users WHERE name = '{name}'").fetchone()
'''

TESTS = '''\
import os
import unittest
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

from handlers.user import app


def call(query):
    env = {}
    setup_testing_defaults(env)
    env["QUERY_STRING"] = urlencode(query)
    seen = {}

    def start(status, headers, exc_info=None):
        seen["status"] = int(status.split()[0])

    b"".join(app(env, start))
    return seen["status"]


class UserTests(unittest.TestCase):
    def test_r1(self):
        self.assertEqual(call({"name": "bad!"}), 400)

    def test_r2(self):
        self.assertEqual(call({"name": "alice"}), 200)

    def test_r3(self):
        self.assertEqual(call({"name": "bob"}), 404)

    def test_r4(self):
        self.assertEqual(call({"name": "x' OR '1'='1"}), 400)

    def test_r5(self):
        self.assertIsNone(os.environ.get("CUSTOM_LLM_KEY"))
'''

# The faulty test from the first real run: '' is in every string.
FAULTY_TEST = TESTS.replace(
    '        self.assertEqual(call({"name": "bad!"}), 400)',
    '        self.assertNotIn("", "{}")')

TODAY = dt.date(2026, 10, 28)
HAS_COVERAGE = importlib.util.find_spec("coverage") is not None


def run(code=GOOD, tests=TESTS, today=TODAY, timeout=60, analyzer=None):
    spec = load_spec(EXAMPLE)
    reqs = requirements_from(spec)
    d = design(spec, reqs)
    files = {"handlers/__init__.py": "", "handlers/user.py": code,
             "tests/__init__.py": "", "tests/test_user.py": tests}
    return verify(spec, reqs, d, files, today=today, timeout=timeout, analyzer=analyzer)


def status(result, rid):
    return [r for r in result.requirements if r.id == rid][0]


class EndToEndTests(unittest.TestCase):
    def test_good_code_passes(self):
        res = run()
        self.assertEqual([r.status for r in res.requirements], ["passed"] * 5, res.to_dict())
        self.assertEqual(res.code_verdict, "passed", res.problems)
        self.assertEqual(res.problems, ())

    def test_dollar_bug_is_caught_by_the_attack_not_the_model_test(self):
        res = run(code=DOLLAR_BUG)
        r1 = status(res, "R1")
        self.assertEqual(r1.status, "failed")
        failing = [e for e in r1.evidence if e.status == "fail"]
        self.assertEqual([e.name for e in failing], ["trailing newline"])
        self.assertEqual([e.status for e in r1.evidence if e.source == "model-test"], ["pass"])
        self.assertEqual(res.code_verdict, "failed")

    def test_logging_raw_input_fails_r5_twice(self):
        res = run(code=LOGS_INPUT)
        r5 = status(res, "R5")
        self.assertEqual(r5.status, "failed")
        sources = {e.source for e in r5.evidence if e.status == "fail"}
        self.assertEqual(sources, {"rule", "attack"})

    def test_sql_built_with_fstring_fails_r4(self):
        res = run(code=SQL_FSTRING)
        r4 = status(res, "R4")
        self.assertEqual(r4.status, "failed")
        self.assertIn("f-string", [e for e in r4.evidence if e.source == "rule"][0].detail)

    def test_faulty_model_test_with_good_code_needs_verification(self):
        res = run(tests=FAULTY_TEST)
        r1 = status(res, "R1")
        self.assertEqual(r1.status, "needs_verification")
        self.assertIn("test may be wrong", r1.note)
        self.assertEqual(res.code_verdict, "needs_verification")

    def test_api_key_is_not_visible_to_generated_code(self):
        with mock.patch.dict(os.environ, {"CUSTOM_LLM_KEY": "sk-should-not-leak"}):
            res = run()
        self.assertEqual(status(res, "R5").status, "passed", res.to_dict())

    def test_spec_age(self):
        self.assertFalse(run(today=TODAY).spec_stale)
        old = run(today=dt.date(2027, 2, 1))
        self.assertTrue(old.spec_stale)
        self.assertEqual(old.spec_age_days, 97)

    def test_coverage(self):
        res = run()
        if HAS_COVERAGE:
            self.assertIn(res.coverage_status, ("ok", "below"))
        else:
            self.assertEqual(res.coverage_status, "skipped")
            self.assertIn("not installed", res.coverage_note)

    def test_code_that_hangs_times_out(self):
        res = run(code="while True:\n    pass\n", timeout=3)
        self.assertTrue(any("timeout" in p for p in res.problems), res.problems)
        self.assertEqual(res.code_verdict, "needs_verification")
        self.assertIn(status(res, "R2").status, ("not_verified",))

    def test_test_file_that_does_not_import(self):
        res = run(tests="import no_such_module\n")
        self.assertTrue(any("could not load" in p or "no model test ran" in p
                            for p in res.problems), res.problems)


class AnalyzerIntegrationTests(unittest.TestCase):
    def test_not_asked_means_no_analyzer_block(self):
        self.assertIsNone(run().analyzer)

    def test_failed_analyzer_fails_the_code(self):
        seen = {}

        def fake(files):
            seen.update(files)
            return AnalyzerResult("failed", note="1 error")

        res = run(analyzer=fake)
        self.assertEqual(list(seen), ["handlers/user.py"])
        self.assertEqual(res.code_verdict, "failed")
        self.assertEqual(res.to_dict()["analyzer"]["status"], "failed")

    def test_passed_analyzer_keeps_the_verdict(self):
        self.assertEqual(run(analyzer=lambda f: AnalyzerResult("passed")).code_verdict, "passed")

    def test_analyzer_error_needs_verification(self):
        res = run(analyzer=lambda f: AnalyzerResult("error", note="timeout"))
        self.assertEqual(res.code_verdict, "needs_verification")
        self.assertTrue(any(p.startswith("analyzer:") for p in res.problems))

    def test_skipped_analyzer_is_noted_not_blocking(self):
        res = run(analyzer=lambda f: AnalyzerResult("skipped", note="command not found: vishap"))
        self.assertEqual(res.code_verdict, "passed")
        self.assertTrue(any("analyzer skipped" in n for n in res.notes))


class NotesTests(unittest.TestCase):
    def test_500_on_valid_input_is_noted(self):
        code = GOOD.replace('    if name not in USERS:', '    raise RuntimeError("no db")\n    if name not in USERS:')
        res = run(code=code)
        self.assertTrue(any("valid input gave a server error" in n for n in res.notes), res.notes)


class RuleTests(unittest.TestCase):
    def test_parse_rule(self):
        r = parse_rule("1-64 letters and digits")
        self.assertEqual((r.lo, r.hi, r.kind), (1, 64, "letters and digits"))
        self.assertIsNone(parse_rule("short names only"))
        self.assertIsNone(parse_rule(None))

    def test_cases_include_trailing_newline_for_query(self):
        cases = input_cases({"name": "name", "in": "query", "rule": "1-64 letters and digits"})
        labels = [c[0] for c in cases]
        self.assertIn("trailing newline", labels)
        self.assertIn("length 65", labels)
        self.assertEqual([c[1] for c in cases if c[0] == "length 64"], ["accept"])

    def test_no_newline_case_for_headers(self):
        cases = input_cases({"name": "x", "in": "header", "rule": "1-8 digits"})
        self.assertNotIn("trailing newline", [c[0] for c in cases])
        self.assertIn("letter", [c[0] for c in cases])


class StaticCheckTests(unittest.TestCase):
    def sql(self, code):
        return sql_findings(ast.parse(code))

    def log(self, code):
        return log_findings(ast.parse(code))

    def test_sql_constant_and_parameter_pass(self):
        self.assertEqual(self.sql('Q = "SELECT 1 WHERE a = ?"\nc.execute(Q, (x,))'), [])
        self.assertEqual(self.sql('c.execute("SELECT 1 WHERE a = ?", (x,))'), [])

    def test_sql_built_strings_fail(self):
        for code in ('c.execute(f"SELECT {x}")',
                     'c.execute("SELECT %s" % x)',
                     'c.execute("SELECT " + x)',
                     'c.execute("SELECT {}".format(x))',
                     'q = f"SELECT {x}"\nc.execute(q)'):
            with self.subTest(code=code):
                self.assertEqual(len(self.sql(code)), 1)

    def test_log_of_request_data_fails(self):
        for code in ('logging.info(request.args["name"])',
                     'name = request.args.get("name")\nlogger.warning("x %s", name)',
                     'n = request.args.get("n")\nm = n.strip()\nprint(m)',
                     'current_app.logger.info("%s", request.args)'):
            with self.subTest(code=code):
                self.assertEqual(len(self.log(code)), 1)

    def test_log_of_wsgi_environ_fails(self):
        code = 'qs = parse_qs(environ["QUERY_STRING"])\nname = qs["name"][0]\nlogging.info(name)'
        self.assertEqual(len(self.log(code)), 1)

    def test_log_without_request_data_passes(self):
        self.assertEqual(self.log('logging.info("started")\nname = request.args.get("n")\nlookup(name)'), [])


if __name__ == "__main__":
    unittest.main()
