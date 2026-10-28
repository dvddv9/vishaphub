# -*- coding: utf-8 -*-
"""Split submitted code into chunks that each fit one focused LLM pass.

Why: one big prompt for a whole file spends its output budget on the loudest problems (SQL injection,
secrets) and cuts the rest off. A focused pass over a few functions does not.

Rules
-----
* Python is split on top-level functions / classes (AST); anything else, or a file that does not parse,
  is split on blank lines near the size limit.
* Every chunk repeats the module header (imports and module-level assignments before the first def),
  so a function that uses ``API_KEY`` or ``sqlite3`` is read with its context.
* Lines are numbered with the ORIGINAL line numbers (``  42| code``) so the model reports lines that
  match the user's file. The prefix is not part of the code.
"""
from __future__ import annotations

import ast

MAX_CHARS = 6000
MAX_CHUNKS = 6
HEADER_CHARS = 1200


def _numbered(lines: list, start: int) -> str:
    return "\n".join(f"{start + i:>5}| {ln}" for i, ln in enumerate(lines))


def _python_units(code: str):
    """[(start_line, end_line)] for each top-level def/class, plus the header end line."""
    tree = ast.parse(code)
    units = []
    header_end = 0
    for node in tree.body:
        start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        end = getattr(node, "end_lineno", node.lineno)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            units.append((start, end))
        elif not units:
            header_end = end
    return units, header_end


def _line_units(lines: list, size: int):
    """Fallback: cut at a blank line once a unit is longer than ``size`` characters."""
    units, start, acc = [], 1, 0
    for i, ln in enumerate(lines, start=1):
        acc += len(ln) + 1
        if acc >= size and not ln.strip():
            units.append((start, i))
            start, acc = i + 1, 0
    if start <= len(lines):
        units.append((start, len(lines)))
    return units, 0


def split_code(material: str, language: str = "python", max_chars: int = MAX_CHARS,
               max_chunks: int = MAX_CHUNKS) -> list:
    """List of ``{"start", "end", "functions", "text"}``; empty when there is nothing to split."""
    material = material or ""
    lines = material.splitlines()
    if not lines:
        return []
    units, header_end = [], 0
    if language == "python":
        try:
            units, header_end = _python_units(material)
        except (SyntaxError, ValueError, RecursionError):
            units = []
    if not units:
        units, header_end = _line_units(lines, max_chars)
    header = ""
    if header_end:
        header = _numbered(lines[:header_end], 1)[:HEADER_CHARS]

    def unit_text(a, b):
        return _numbered(lines[a - 1:b], a)

    names = {}
    if language == "python":
        try:
            for node in ast.parse(material).body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names[node.lineno] = node.name
        except Exception:
            names = {}

    chunks, cur = [], None
    for a, b in units:
        body = unit_text(a, b)
        fn = [n for ln, n in names.items() if a <= ln <= b]
        if cur is not None and len(cur["body"]) + len(body) + 1 <= max_chars:
            cur["body"] += "\n" + body
            cur["end"] = b
            cur["functions"] += fn
        else:
            if cur is not None:
                chunks.append(cur)
            cur = {"start": a, "end": b, "body": body, "functions": list(fn)}
    if cur is not None:
        chunks.append(cur)

    if len(chunks) > max_chunks:          # keep the cost bounded: merge the tail into the last chunk
        tail = chunks[max_chunks - 1:]
        merged = {"start": tail[0]["start"], "end": tail[-1]["end"],
                  "body": "\n".join(c["body"] for c in tail),
                  "functions": [f for c in tail for f in c["functions"]]}
        chunks = chunks[:max_chunks - 1] + [merged]

    out = []
    for c in chunks:
        text = (header + "\n...\n" if header else "") + c["body"]
        out.append({"start": c["start"], "end": c["end"], "functions": c["functions"], "text": text})
    return out
