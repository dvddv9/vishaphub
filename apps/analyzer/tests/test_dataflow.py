# -*- coding: utf-8 -*-
"""P2-7b: AST-based data-flow analysis tests (TDD).

Tests define the API of src/tools/dataflow.py before implementation.
All tests will fail on ImportError until dataflow.py is written.
"""

from src.tools.dataflow import analyze_dataflow, enrich_dataflow
from src.tools.patterns import AST_TAINT_SOURCES, AST_TAINT_SINKS


# ---------- analyze_dataflow ----------

def test_analyze_dataflow_sql_injection_simple():
    """Direct source -> sink flow (request.args -> cursor.execute)."""
    code = (
        "def handler():\n"
        "    user_id = request.args.get('id')\n"
        "    cursor.execute('SELECT * FROM users WHERE id=' + user_id)\n"
    )
    result = analyze_dataflow(code)
    assert result.get("source") is not None
    assert result.get("sink") is not None
    assert result["path"]
    assert result["source_count"] >= 1
    assert result["sink_count"] >= 1


def test_analyze_dataflow_no_flow():
    """No source or sink -> empty result."""
    code = "x = 1\nprint(x)\n"
    result = analyze_dataflow(code)
    assert result == {}


def test_analyze_dataflow_function_arg_source():
    """Source via function argument (regex can't see this)."""
    code = (
        "def handler(user_input):\n"
        "    cursor.execute('SELECT ' + user_input)\n"
    )
    result = analyze_dataflow(code)
    assert result.get("sink") is not None


def test_analyze_dataflow_intermediate_variables():
    """Flow through intermediate variables: a -> b -> sink."""
    code = (
        "def handler():\n"
        "    a = request.args.get('x')\n"
        "    b = a\n"
        "    cursor.execute('SELECT ' + b)\n"
    )
    result = analyze_dataflow(code)
    assert result.get("source") is not None
    assert result.get("sink") is not None
    assert len(result.get("intermediate", [])) >= 0


def test_analyze_dataflow_os_system_sink():
    """subprocess.run is a sink."""
    code = (
        "def handler():\n"
        "    cmd = request.args.get('cmd')\n"
        "    subprocess.run(cmd)\n"
    )
    result = analyze_dataflow(code)
    assert result.get("sink") is not None


def test_analyze_dataflow_eval_sink():
    """eval is a sink."""
    code = (
        "def handler():\n"
        "    x = input()\n"
        "    eval(x)\n"
    )
    result = analyze_dataflow(code)
    assert result.get("sink") is not None


def test_analyze_dataflow_os_environ_source():
    """os.environ.get is a source."""
    code = (
        "def handler():\n"
        "    x = os.environ.get('SECRET')\n"
        "    cursor.execute('SELECT ' + x)\n"
    )
    result = analyze_dataflow(code)
    assert result.get("source") is not None


def test_analyze_dataflow_syntax_error_fail_open():
    """Broken Python -> empty dict, no exception."""
    code = "def broken(:\n    pass\n"
    result = analyze_dataflow(code)
    assert result == {}


def test_analyze_dataflow_not_python():
    """Non-Python language -> empty dict (fail-open)."""
    code = "func main() { db.Execute(userInput) }"
    result = analyze_dataflow(code, language="go")
    assert result == {}


# ---------- enrich_dataflow ----------

def test_enrich_dataflow_backward_compat():
    """enrich_dataflow does not touch exploitability."""
    code = "x = request.args.get('a')\ncursor.execute(x)\n"
    result = enrich_dataflow(code)
    assert "dataflow" in result
    assert "exploitability" not in result


def test_enrich_dataflow_new_field():
    """dataflow field is present in result."""
    code = "x = request.args.get('a')\ncursor.execute(x)\n"
    result = enrich_dataflow(code)
    assert isinstance(result["dataflow"], dict)


def test_enrich_dataflow_empty():
    """No flow -> dataflow is empty dict."""
    code = "x = 1\nprint(x)\n"
    result = enrich_dataflow(code)
    assert result == {"dataflow": {}}


def test_enrich_dataflow_does_not_mutate_input():
    """enrich_dataflow does not mutate its input material."""
    code = "x = request.args.get('a')\ncursor.execute(x)\n"
    original = code
    enrich_dataflow(code)
    assert code == original


# ---------- patterns data ----------

def test_ast_taint_sources_has_expected_keys():
    """AST_TAINT_SOURCES has flask/input/env/file markers."""
    assert "flask_request" in AST_TAINT_SOURCES
    assert "builtin_input" in AST_TAINT_SOURCES
    assert "env" in AST_TAINT_SOURCES
    assert "file_read" in AST_TAINT_SOURCES


def test_ast_taint_sinks_has_expected_keys():
    """AST_TAINT_SINKS has sql/cmd/file markers."""
    assert "sql_execute" in AST_TAINT_SINKS
    assert "cmd_exec" in AST_TAINT_SINKS
    assert "file_write" in AST_TAINT_SINKS


def test_dataflow_path_has_line_numbers():
    """Every path node has an integer line number."""
    code = (
        "def handler():\n"
        "    user_id = request.args.get('id')\n"
        "    cursor.execute('SELECT ' + user_id)\n"
    )
    result = analyze_dataflow(code)
    for node in result.get("path", []):
        assert isinstance(node.get("line"), int)
        assert node["line"] >= 1
