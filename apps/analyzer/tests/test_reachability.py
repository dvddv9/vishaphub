# -*- coding: utf-8 -*-
"""Tests for src/tools/reachability.py (P2-7).

Test-first: this file is written BEFORE the module.
Expect ImportError on first run.
"""

from src.tools.reachability import (
    find_entry_points,
    find_taint_sources,
    trace_taint,
    enrich_exploitability,
)


# --- find_entry_points ---

def test_find_entry_points_python_flask():
    code = '@app.route("/users")\ndef list_users():\n    pass\n'
    eps = find_entry_points(code, language="python")
    assert len(eps) >= 1
    assert eps[0]["line"] == 1
    assert "app.route" in eps[0]["content"]
    assert eps[0]["type"] == "entry_point"


def test_find_entry_points_python_main():
    code = 'def foo():\n    pass\n\nif __name__ == "__main__":\n    foo()\n'
    eps = find_entry_points(code, language="python")
    lines = [e["line"] for e in eps]
    assert 4 in lines


def test_find_entry_points_go():
    code = 'package main\n\nfunc main() {\n    fmt.Println("hi")\n}\n'
    eps = find_entry_points(code, language="go")
    assert len(eps) >= 1
    assert eps[0]["line"] == 3


def test_find_entry_points_js():
    code = 'const express = require("express");\napp.get("/users", handler);\n'
    eps = find_entry_points(code, language="js")
    assert len(eps) >= 1
    assert eps[0]["line"] == 2


def test_find_entry_points_unknown_language():
    code = "puts 'hello'\n"
    eps = find_entry_points(code, language="ruby")
    assert eps == []


# --- find_taint_sources ---

def test_find_taint_sources_flask():
    code = 'def handler():\n    email = request.args.get("email")\n    return email\n'
    sources = find_taint_sources(code)
    assert len(sources) >= 1
    assert sources[0]["line"] == 2
    assert "request.args" in sources[0]["content"]


def test_find_taint_sources_negative():
    code = "x = 1 + 2\nprint(x)\n"
    sources = find_taint_sources(code)
    assert sources == []


# --- trace_taint ---

def test_trace_taint_source_to_sink():
    code = (
        "def handler():\n"                              # 1
        '    email = request.args.get("email")\n'       # 2 source
        "    query = build_query(email)\n"              # 3
        "    cursor = db.cursor()\n"                    # 4
        "    cursor.execute(query)\n"                   # 5 sink
        "    return cursor.fetchall()\n"                # 6
    )
    result = trace_taint(code)
    assert result["reachable"] is True
    assert result["source_count"] >= 1
    path = result["path"]
    assert len(path) >= 2
    types = [p["type"] for p in path]
    assert "source" in types
    assert "sink" in types


def test_trace_taint_no_sources():
    code = "def foo():\n    return 42\n"
    result = trace_taint(code)
    assert result["reachable"] is False
    assert result["path"] == []
    assert result["source_count"] == 0


# --- enrich_exploitability ---

def test_enrich_exploitability_backward_compat():
    code = '@app.route("/")\ndef h():\n    return 1\n'
    old = {
        "reachable": True,
        "auth_required": False,
        "exploit_path": "web -> auth? -> none",
        "blast_radius": "none",
        "entry_points": ["web"],
        "blast_indicators": [],
    }
    new = enrich_exploitability(code, old)
    # old fields preserved
    assert new["reachable"] == old["reachable"]
    assert new["auth_required"] == old["auth_required"]
    assert new["exploit_path"] == old["exploit_path"]
    assert new["blast_radius"] == old["blast_radius"]
    assert new["entry_points"] == old["entry_points"]
    assert new["blast_indicators"] == old["blast_indicators"]


def test_enrich_exploitability_new_fields():
    code = (
        "def handler():\n"
        '    email = request.args.get("email")\n'
        "    cursor.execute(email)\n"
    )
    old = {
        "reachable": True,
        "auth_required": False,
        "exploit_path": "web -> none",
        "blast_radius": "medium",
        "entry_points": ["web"],
        "blast_indicators": ["db"],
    }
    new = enrich_exploitability(code, old)
    # new fields
    assert "path" in new
    assert isinstance(new["path"], list)
    assert "source_count" in new
    assert new["source_count"] >= 1
    assert "sources" in new
    assert "entry_points_lines" in new
    assert "sinks" in new
