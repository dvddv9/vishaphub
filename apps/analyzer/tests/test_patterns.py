# -*- coding: utf-8 -*-
"""Tests for P2-7 pattern extensions in patterns.py.

Covers: go/js entry points, TAINT_SOURCES, TAINT_SINKS.
"""
from src.tools.patterns import EXPLOIT_PATTERNS, TAINT_SOURCES, TAINT_SINKS


# --- Entry points: go ---

def test_entrypoint_go_main():
    code = "func main() {\n    fmt.Println(\"hi\")\n}"
    assert EXPLOIT_PATTERNS["entrypoint_go_main"].search(code)


def test_entrypoint_go_http():
    code = 'http.HandleFunc("/api", handler)'
    assert EXPLOIT_PATTERNS["entrypoint_go_http"].search(code)


# --- Entry points: js ---

def test_entrypoint_js_route():
    code = 'app.get("/users", (req, res) => {})'
    assert EXPLOIT_PATTERNS["entrypoint_js_route"].search(code)
    code2 = 'router.post("/login", handler)'
    assert EXPLOIT_PATTERNS["entrypoint_js_route"].search(code2)


# --- Taint sources ---

def test_taint_sources_flask():
    code = "email = request.args.get('email')\nname = request.form['name']"
    assert TAINT_SOURCES["source_flask"].search(code)


def test_taint_sources_generic():
    code = "user_input = input('> ')\nargs = sys.argv\nenv = os.environ['HOME']"
    assert TAINT_SOURCES["source_generic"].search(code)


def test_taint_sources_negative():
    code = "x = 1 + 2\nprint(x)"
    assert not TAINT_SOURCES["source_flask"].search(code)
    assert not TAINT_SOURCES["source_generic"].search(code)


# --- Taint sinks ---

def test_taint_sinks_sql():
    code = "cursor.execute(query)\ndb.query('SELECT *')"
    assert TAINT_SINKS["sink_sql"].search(code)


def test_taint_sinks_cmd():
    code = "os.system(cmd)\nsubprocess.run(args)\nresult = eval(expr)"
    assert TAINT_SINKS["sink_cmd"].search(code)


def test_taint_sinks_fs():
    code = "f = open('/tmp/x')\nos.remove(path)"
    assert TAINT_SINKS["sink_fs"].search(code)
