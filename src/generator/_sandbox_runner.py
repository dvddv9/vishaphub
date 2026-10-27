"""Runs in a subprocess next to the generated files. Standard library only;
Flask is used when it is installed.

    python -X utf8 _vg_runner.py tests|attacks <plan.json> <out.json>

tests    run the model's tests with unittest (under coverage when installed)
attacks  send Verify's own requests to the app and watch logs and output

This file is copied into the temporary folder by verify.py; it is not
imported by the generator itself.
"""

import contextlib
import importlib
import io
import json
import logging
import os
import sys
import unittest
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


class Collect(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.status = {}
        self.notes = {}

    def _set(self, test, st, err=None):
        name = getattr(test, "_testMethodName", None) or str(test)
        if self.status.get(name) in ("fail", "error") and st == "pass":
            return
        self.status[name] = st
        if err is not None:
            self.notes[name] = self._exc_info_to_string(err, test)[-1500:]

    def addSuccess(self, test):
        self._set(test, "pass")

    def addFailure(self, test, err):
        self._set(test, "fail", err)

    def addError(self, test, err):
        self._set(test, "error", err)

    def addSkip(self, test, reason):
        self._set(test, "skipped")

    def addExpectedFailure(self, test, err):
        self._set(test, "pass")

    def addUnexpectedSuccess(self, test):
        self._set(test, "fail")

    def addSubTest(self, test, subtest, err):
        if err is not None:
            kind = "fail" if issubclass(err[0], test.failureException) else "error"
            self._set(test, kind, err)


def run_tests(plan):
    tests_dir = os.path.join(ROOT, plan["tests_dir"])
    top = ROOT if os.path.exists(os.path.join(tests_dir, "__init__.py")) else None
    cov, cov_note = None, None
    try:
        import coverage
        cov = coverage.Coverage(
            data_file=None,
            include=[os.path.join(ROOT, p) for p in plan["code_files"]])
        cov.start()
    except ImportError:
        cov_note = "coverage is not installed"
    except Exception as e:  # noqa: BLE001
        cov, cov_note = None, f"coverage did not start: {e}"

    result = Collect()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            suite = unittest.defaultTestLoader.discover(tests_dir, top_level_dir=top)
            suite.run(result)
    finally:
        if cov is not None:
            cov.stop()

    percent = None
    if cov is not None:
        try:
            percent = round(cov.report(file=io.StringIO()), 1)
        except Exception as e:  # noqa: BLE001
            cov_note = f"coverage report failed: {e}"
    return {"tests": result.status, "notes": result.notes,
            "coverage": percent, "coverage_note": cov_note}


def find_app(mod):
    try:
        import flask
    except ImportError:
        flask = None
    if flask is not None:
        for v in vars(mod).values():
            if isinstance(v, flask.Flask):
                return v, "flask"
        for v in vars(mod).values():
            if isinstance(v, flask.Blueprint):
                app = flask.Flask("vishap_generator_verify")
                app.register_blueprint(v)
                return app, "flask-blueprint"
    for name in ("app", "application"):
        v = getattr(mod, name, None)
        if callable(v):
            return v, "wsgi"
    return None, None


def single_route(app):
    url_map = getattr(app, "url_map", None)
    if url_map is None:
        return None
    rules = [r for r in url_map.iter_rules() if r.endpoint != "static"]
    if len(rules) != 1:
        return None
    methods = sorted(m for m in rules[0].methods if m not in ("HEAD", "OPTIONS"))
    return (methods[0] if methods else "GET"), rules[0].rule


def do_request(app, method, path, req):
    env = {}
    setup_testing_defaults(env)
    env["REQUEST_METHOD"] = method
    env["PATH_INFO"] = path
    env["QUERY_STRING"] = urlencode(req.get("query", {}))
    env["wsgi.input"] = io.BytesIO(b"")
    env["CONTENT_LENGTH"] = "0"
    for k, v in req.get("headers", {}).items():
        env["HTTP_" + k.upper().replace("-", "_")] = v

    captured = io.StringIO()
    handler = logging.StreamHandler(captured)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    seen = {}

    def start_response(status, headers, exc_info=None):
        seen["code"] = int(str(status).split()[0])
        return lambda data: None

    out = {"id": req["id"], "status": None, "error": None, "marker_seen": False}
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            body = app(env, start_response)
            try:
                for _ in body:
                    pass
            finally:
                close = getattr(body, "close", None)
                if close:
                    close()
        out["status"] = seen.get("code")
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}"
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
    marker = req.get("marker")
    if marker:
        text = captured.getvalue() + stdout.getvalue() + stderr.getvalue()
        out["marker_seen"] = marker in text
    return out


def run_attacks(plan):
    out = {"requests": [], "app": None, "route": None, "error": None}
    try:
        mod = importlib.import_module(plan["module"])
    except Exception as e:  # noqa: BLE001
        out["error"] = f"import of {plan['module']} failed: {type(e).__name__}: {e}"
        return out
    app, kind = find_app(mod)
    if app is None:
        out["error"] = "no Flask app, Blueprint or WSGI callable named app found"
        return out
    method, path = plan.get("method"), plan.get("path")
    if not path:
        found = single_route(app)
        if found is None:
            out["error"] = "route unknown: give route in the spec"
            return out
        method, path = found
    out["app"], out["route"] = kind, f"{method} {path}"
    for req in plan["requests"]:
        out["requests"].append(do_request(app, method, path, req))
    return out


def main():
    mode, plan_path, out_path = sys.argv[1:4]
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    data = run_tests(plan) if mode == "tests" else run_attacks(plan)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f)


if __name__ == "__main__":
    main()
