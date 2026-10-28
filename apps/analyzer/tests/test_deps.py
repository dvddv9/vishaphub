# -*- coding: utf-8 -*-
"""Tests for inter-file analysis (P1-6)."""
from pathlib import Path

from src.tools.deps import (
    find_imports,
    build_import_graph,
    resolve_dependencies,
    collect_context_files,
    _is_local_module,
)


def _write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_find_imports_basic(tmp_path):
    f = tmp_path / "x.py"
    _write(f, "import os\nimport json\nfrom src.tools import diff\n")
    imports = find_imports(str(f))
    assert "os" in imports
    assert "json" in imports
    assert "src.tools" in imports


def test_find_imports_syntax_error(tmp_path):
    f = tmp_path / "bad.py"
    _write(f, "def foo(:\n  pass\n")
    assert find_imports(str(f)) == []


def test_find_imports_missing_file(tmp_path):
    assert find_imports(str(tmp_path / "nope.py")) == []


def test_find_imports_deduplicates(tmp_path):
    f = tmp_path / "x.py"
    _write(f, "import os\nimport os\nfrom os import path\n")
    imports = find_imports(str(f))
    assert imports.count("os") == 1


def test_is_local_module_stdlib():
    assert _is_local_module("os", "/tmp") is False
    assert _is_local_module("json", "/tmp") is False


def test_is_local_module_local_file(tmp_path):
    _write(tmp_path / "local.py", "x = 1")
    assert _is_local_module("local", str(tmp_path)) is True


def test_is_local_module_package(tmp_path):
    _write(tmp_path / "pkg" / "__init__.py", "")
    assert _is_local_module("pkg", str(tmp_path)) is True


def test_build_import_graph(tmp_path):
    _write(tmp_path / "a.py", "import b\nimport os\n")
    _write(tmp_path / "b.py", "import c\n")
    _write(tmp_path / "c.py", "x = 1\n")
    graph = build_import_graph(str(tmp_path))
    assert "a.py" in graph
    assert "b" in graph["a.py"]
    assert "os" not in graph["a.py"]  # stdlib filtered


def test_build_import_graph_missing_root():
    assert build_import_graph("/nonexistent/path") == {}


def test_resolve_dependencies_depth_1(tmp_path):
    _write(tmp_path / "a.py", "import b\n")
    _write(tmp_path / "b.py", "import c\n")
    _write(tmp_path / "c.py", "x = 1\n")
    graph = build_import_graph(str(tmp_path))
    deps = resolve_dependencies("a.py", graph, depth=1)
    assert "b.py" in deps
    assert "c.py" not in deps


def test_resolve_dependencies_depth_2(tmp_path):
    _write(tmp_path / "a.py", "import b\n")
    _write(tmp_path / "b.py", "import c\n")
    _write(tmp_path / "c.py", "x = 1\n")
    graph = build_import_graph(str(tmp_path))
    deps = resolve_dependencies("a.py", graph, depth=2)
    assert "b.py" in deps
    assert "c.py" in deps


def test_resolve_dependencies_circular(tmp_path):
    _write(tmp_path / "a.py", "import b\n")
    _write(tmp_path / "b.py", "import a\n")
    graph = build_import_graph(str(tmp_path))
    deps = resolve_dependencies("a.py", graph, depth=5)
    # Should not infinite loop
    assert "b.py" in deps
    assert "a.py" not in deps  # excludes self


def test_resolve_dependencies_no_graph():
    assert resolve_dependencies("a.py", {}, depth=2) == []


def test_collect_context_files_basic(tmp_path):
    _write(tmp_path / "a.py", "import b\nprint('a')\n")
    _write(tmp_path / "b.py", "print('b')\n")
    ctx = collect_context_files(str(tmp_path), "a.py", depth=1)
    assert "b.py" in ctx
    assert "print('b')" in ctx["b.py"]


def test_collect_context_files_max_files(tmp_path):
    for i in range(20):
        _write(tmp_path / f"f{i}.py", "x = 1\n")
    _write(tmp_path / "a.py", "\n".join(f"import f{i}" for i in range(20)))
    ctx = collect_context_files(str(tmp_path), "a.py", depth=1, max_files=5)
    assert len(ctx) <= 5


def test_collect_context_files_truncates(tmp_path):
    _write(tmp_path / "a.py", "import b\n")
    _write(tmp_path / "b.py", "x = 1\n" * 5000)
    ctx = collect_context_files(str(tmp_path), "a.py", depth=1, max_file_bytes=100)
    assert "b.py" in ctx
    assert "[truncated]" in ctx["b.py"]
    assert len(ctx["b.py"]) < 200


def test_collect_context_files_missing_target(tmp_path):
    _write(tmp_path / "a.py", "x = 1\n")
    assert collect_context_files(str(tmp_path), "nonexistent.py") == {}
