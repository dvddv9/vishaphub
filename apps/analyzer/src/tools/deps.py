# -*- coding: utf-8 -*-
"""Inter-file analysis: Python import graph (P1-6).

Builds a dependency graph via AST, resolves imports to depth N, and
collects file contents for Stage 2 context. Tolerant to syntax errors,
circular imports, and missing files.

Security: max_files and max_file_bytes caps to avoid prompt bloat.
Ignores stdlib imports (os, sys, json, ...).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# Limits
DEFAULT_DEPTH = 2
DEFAULT_MAX_FILES = 10
DEFAULT_MAX_FILE_BYTES = 10_000

# Python stdlib modules (subset -- enough to filter local vs external)
_STDLIB = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else {
    "os", "sys", "json", "re", "ast", "pathlib", "typing", "dataclasses",
    "datetime", "collections", "itertools", "functools", "subprocess",
    "hashlib", "base64", "logging", "unittest", "io", "time", "math",
    "random", "string", "textwrap", "abc", "enum", "contextlib",
}


def find_imports(file_path: str) -> list:
    """Extract top-level module imports from a Python file.

    Returns list of dotted module names (e.g. "src.tools.diff").
    Returns [] on syntax error, missing file, or non-Python content.
    """
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return []
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.append(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                imports.append(node.module)

    seen = []
    for imp in imports:
        if imp and imp not in seen:
            seen.append(imp)
    return seen


def _is_local_module(imp: str, root: str) -> bool:
    """True if import resolves to a .py file under root."""
    if not imp:
        return False
    top = imp.split(".")[0]
    if top in _STDLIB:
        return False
    # Try as a file: "src.tools.diff" -> "src/tools/diff.py"
    rel = imp.replace(".", "/") + ".py"
    if (Path(root) / rel).is_file():
        return True
    # Try as a package: "src.tools" -> "src/tools/__init__.py"
    rel_init = imp.replace(".", "/") + "/__init__.py"
    if (Path(root) / rel_init).is_file():
        return True
    return False


def build_import_graph(root: str) -> dict:
    """Walk root, build {relative_file: [local_imports]}.

    Only local imports (files under root) are included.
    Skips __init__.py files (noise).
    """
    root_p = Path(root)
    if not root_p.exists() or not root_p.is_dir():
        return {}

    graph = {}
    for py in root_p.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        try:
            rel = str(py.relative_to(root_p)).replace("\\", "/")
        except ValueError:
            continue
        imports = find_imports(str(py))
        local = [imp for imp in imports if _is_local_module(imp, root)]
        graph[rel] = local
    return graph


def resolve_dependencies(
    file_path: str,
    graph: dict,
    depth: int = DEFAULT_DEPTH,
) -> list:
    """BFS over import graph up to depth levels.

    Args:
        file_path: relative path (as in graph keys), e.g. "api.py"
        graph: {rel_path: [imports]}
        depth: 0 = self only; 1 = direct deps; 2 = deps of deps.

    Returns:
        List of relative paths (excluding file_path itself if depth >= 1).
    """
    if not graph:
        return []
    norm = file_path.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]

    visited = {norm}
    current = [norm]

    for _ in range(max(0, depth)):
        next_level = []
        for f in current:
            for imp in graph.get(f, []):
                rel = imp.replace(".", "/") + ".py"
                # Also try package form
                if rel not in graph:
                    rel_init = imp.replace(".", "/") + "/__init__.py"
                    if rel_init in graph:
                        rel = rel_init
                    else:
                        continue
                if rel in visited:
                    continue
                visited.add(rel)
                next_level.append(rel)
        current = next_level
        if not current:
            break

    visited.discard(norm)
    return sorted(visited)


def collect_context_files(
    root: str,
    filename: str,
    depth: int = DEFAULT_DEPTH,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    graph: dict = None,
) -> dict:
    """Collect file contents of imported modules.

    Args:
        root: project root path
        filename: target file (relative path or basename)
        depth: dependency depth
        max_files: cap on number of files
        max_file_bytes: truncate each file at this size
        graph: pre-built graph (optional, for performance)

    Returns:
        {relative_path: content} -- content truncated to max_file_bytes.
    """
    if graph is None:
        graph = build_import_graph(root)
    if not graph:
        return {}

    # Normalize filename to graph-key form
    norm = filename.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]

    if norm not in graph:
        # Try matching by basename
        candidates = [k for k in graph if Path(k).name == Path(norm).name]
        if not candidates:
            return {}
        norm = candidates[0]

    deps = resolve_dependencies(norm, graph, depth=depth)

    context_files = {}
    root_p = Path(root)
    for dep in deps[:max_files]:
        p = root_p / dep
        if not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(content) > max_file_bytes:
            content = content[:max_file_bytes] + "\n... [truncated]"
        context_files[dep] = content
    return context_files
