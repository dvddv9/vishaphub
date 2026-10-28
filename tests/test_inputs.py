"""Verify's attacks and the COVE probes reach inputs in `body` (a JSON object) and in `path`, not only query and header."""
import datetime as dt
import unittest

from tests.helpers import write_spec
from tests.test_deliver import CLEAN_SPEC

from generator.pipeline import _sandbox_runner as runner
from generator.pipeline.cove import build_probes, run_cove
from generator.pipeline.design import design
from generator.pipeline.intake import requirements_from
from generator.pipeline.verify import ABSENT, default_values, input_cases, make_request, route_has, verify
from generator.tools.spec import load_spec

TODAY = dt.date(2026, 10, 28)
BASE = CLEAN_SPEC.read_text(encoding="utf-8")
BODY_SPEC = BASE.replace("in: query", "in: body").replace("route: GET /user", "route: POST /user")
PATH_SPEC = BASE.replace("in: query", "in: path").replace("route: GET /user", "route: GET /user/<name>")
NO_PLACEHOLDER = BASE.replace("in: query", "in: path")      # route is GET /user: nowhere for the value

HEAD = '''\
import json
import logging
import re

NAME = re.compile(r"[A-Za-z0-9]{1,64}")


def _send(start_response, status, body):
    start_response(status, [("Content-Type", "application/json")])
    return [body.encode()]

'''
BODY_APP = HEAD + '''
def app(environ, start_response):
    try:
        size = int(environ.get("CONTENT_LENGTH") or 0)
        data = json.loads(environ["wsgi.input"].read(size) or b"{}")
    except ValueError:
        return _send(start_response, "400 Bad Request", "{}")
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str) or not NAME.fullmatch(name):
        return _send(start_response, "400 Bad Request", "{}")
    return _send(start_response, "200 OK", '{"id": 1, "name": "alice"}')
'''
PATH_APP = HEAD + '''
def app(environ, start_response):
    name = environ["PATH_INFO"].rsplit("/", 1)[-1]
    if not NAME.fullmatch(name):
        return _send(start_response, "400 Bad Request", "{}")
    return _send(start_response, "200 OK", '{"id": 1, "name": "alice"}')
'''
DOLLAR = ('NAME = re.compile(r"^[A-Za-z0-9]{1,64}$")', "NAME.fullmatch(name)", "NAME.match(name)")


def dollar_bug(code):
    return code.replace('NAME = re.compile(r"[A-Za-z0-9]{1,64}")', DOLLAR[0]).replace(DOLLAR[1], DOLLAR[2])


def prepare(spec_text, code):
    spec = load_spec(write_spec(spec_text))
    reqs = requirements_from(spec)
    d = design(spec, reqs)
    tests = "import unittest\n\n\nclass T(unittest.TestCase):\n" + "".join(
        f"    def test_r{n}(self):\n        self.assertTrue(True)\n\n" for n in range(1, len(reqs) + 1))
    files = {"handlers/__init__.py": "", "handlers/user.py": code, "tests/__init__.py": "", "tests/test_user.py": tests}
    return spec, reqs, d, files


def attacks(spec_text, code, rid="R1"):
    spec, reqs, d, files = prepare(spec_text, code)
    res = verify(spec, reqs, d, files, today=TODAY, coverage="skip")
    if rid == "log":
        rid = next(r.id for r in reqs if "logged" in r.text)
    ev = [e for r in res.requirements if r.id == rid for e in r.evidence if e.source == "attack"]
    return {e.name: e for e in ev}, res


class BodyTests(unittest.TestCase):
    def test_a_good_body_app_passes_every_attack(self):
        ev, _ = attacks(BODY_SPEC, BODY_APP)
        self.assertTrue({"absent", "empty", "length 65", "trailing newline", "quote", "length 1", "length 64"} <= set(ev), set(ev))
        self.assertEqual({e.status for e in ev.values()}, {"pass"}, {k: v.detail for k, v in ev.items() if v.status != "pass"})

    def test_the_dollar_bug_in_a_body_is_caught(self):
        ev, _ = attacks(BODY_SPEC, dollar_bug(BODY_APP))
        self.assertEqual(ev["trailing newline"].status, "fail")
        self.assertEqual(ev["length 1"].status, "pass")

    def test_an_app_that_ignores_a_missing_field_fails_the_absent_attack(self):
        lax = BODY_APP.replace("not isinstance(name, str) or not NAME.fullmatch(name)",
                               "isinstance(name, str) and not NAME.fullmatch(name)")
        ev, _ = attacks(BODY_SPEC, lax)
        self.assertEqual(ev["absent"].status, "fail")

    def test_a_body_input_is_logged_is_caught(self):
        logging_app = BODY_APP.replace("    name = data.get", "    logging.getLogger('x').error('got %s', data)\n    name = data.get")
        ev, _ = attacks(BODY_SPEC, logging_app, rid="log")
        self.assertTrue(any(e.status == "fail" for e in ev.values()), {k: v.status for k, v in ev.items()})

    def test_make_request_puts_the_value_in_the_json_object(self):
        spec = load_spec(write_spec(BODY_SPEC))
        inputs = [i for i, _ in spec.items["inputs"]]
        req = make_request(inputs, default_values(inputs), "R1", "empty", "reject", inputs[0], "")
        self.assertEqual(req["json"], {"name": ""})
        self.assertEqual(req["query"], {})
        self.assertNotIn("path_values", req)
        absent = make_request(inputs, default_values(inputs), "R1", "absent", "reject", inputs[0], ABSENT)
        self.assertEqual(absent["json"], {})


class PathTests(unittest.TestCase):
    def test_a_good_path_app_passes_and_has_no_absent_or_empty(self):
        ev, _ = attacks(PATH_SPEC, PATH_APP)
        self.assertNotIn("absent", ev)
        self.assertNotIn("empty", ev)
        self.assertTrue({"length 65", "trailing newline", "quote", "punctuation"} <= set(ev), set(ev))
        self.assertEqual({e.status for e in ev.values()}, {"pass"}, {k: v.detail for k, v in ev.items() if v.status != "pass"})

    def test_the_dollar_bug_in_a_path_is_caught(self):
        ev, _ = attacks(PATH_SPEC, dollar_bug(PATH_APP))
        self.assertEqual(ev["trailing newline"].status, "fail")

    def test_a_path_input_without_a_placeholder_is_skipped_with_the_reason(self):
        ev, _ = attacks(NO_PLACEHOLDER, PATH_APP)
        self.assertEqual(set(ev), {"-"})
        self.assertEqual(ev["-"].status, "skipped")
        self.assertIn("no placeholder", ev["-"].detail)

    def test_route_has_the_three_spellings(self):
        for route in ("GET /u/<name>", "GET /u/<int:name>", "GET /u/{name}"):
            self.assertTrue(route_has(route, "name"), route)
        for route in ("GET /u", "GET /u/<other>", None):
            self.assertFalse(route_has(route, "name"), route)

    def test_fill_path(self):
        self.assertEqual(runner.fill_path("/u/<name>/x", {"name": "a1\n"}), "/u/a1\n/x")
        self.assertEqual(runner.fill_path("/u/<int:id>", {"id": "12"}), "/u/12")
        self.assertEqual(runner.fill_path("/u/{x}", {"x": "$1\\2"}), "/u/$1\\2")      # a value is never a regex template
        self.assertEqual(runner.fill_path("/u", {}), "/u")

    def test_make_request_puts_the_value_in_the_path(self):
        spec = load_spec(write_spec(PATH_SPEC))
        inputs = [i for i, _ in spec.items["inputs"]]
        req = make_request(inputs, default_values(inputs), "R1", "quote", "reject", inputs[0], "a1'")
        self.assertEqual(req["path_values"], {"name": "a1'"})
        self.assertNotIn("json", req)


class CasesTests(unittest.TestCase):
    def labels(self, where):
        return [c[0] for c in input_cases({"in": where, "name": "n", "rule": "1-8 letters and digits"})]

    def test_each_kind_gets_its_own_cases(self):
        q, b, p, h = (self.labels(w) for w in ("query", "body", "path", "header"))
        self.assertEqual(q, b)
        self.assertIn("trailing newline", p)
        self.assertNotIn("absent", p)
        self.assertNotIn("trailing newline", h)
        self.assertIs([c for c in input_cases({"in": "query", "name": "n", "rule": "1-8 letters and digits"}) if c[0] == "absent"][0][2], ABSENT)


class CoveTests(unittest.TestCase):
    def test_probes_cover_body_and_path_inputs(self):
        for text, where in ((BODY_SPEC, "body"), (PATH_SPEC, "path")):
            spec = load_spec(write_spec(text))
            probes = build_probes(spec, requirements_from(spec))
            self.assertTrue(probes, where)
            self.assertEqual({p.where for p in probes}, {where})

    def test_no_probe_for_a_path_input_without_a_placeholder(self):
        spec = load_spec(write_spec(NO_PLACEHOLDER))
        self.assertEqual(build_probes(spec, requirements_from(spec)), [])

    def test_a_loose_body_app_is_a_mismatch(self):
        spec, reqs, d, files = prepare(BODY_SPEC, BODY_APP.replace('r"[A-Za-z0-9]{1,64}"', 'r"\\w{1,64}"'))
        import json

        def reading(messages, config=None, **kw):
            items = []
            for line in messages[-1]["content"].splitlines():
                line = line.strip()
                if line.startswith('{"id": "P'):
                    p = json.loads(line)
                    items.append({"id": p["id"], "expect": "accept" if p["label"] == "uppercase" else "reject"})
            return json.dumps({"answers": items})
        r = run_cove(spec, reqs, d, files, chat_fn=reading)
        self.assertEqual(r.status, "ok", r.to_dict())
        self.assertTrue(any("another script" in m for m in r.mismatches), r.mismatches)


if __name__ == "__main__":
    unittest.main()
