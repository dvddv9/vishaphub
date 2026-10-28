# -*- coding: utf-8 -*-
"""Who calls whom, inside one Python file: the map a skeptic needs to ask "does anything reach this?".

Entry points are HTTP routes (``@app.route``, ``@router.get`` ...), functions called under
``if __name__ == "__main__"`` and public top-level functions (callable by importers). It never claims more
than a single file can show: ``callers`` lists only callers in this file, and a public function with none is
still an entry point for the code that imports it.
"""
from __future__ import annotations

import ast

_HTTP = {"route", "get", "post", "put", "delete", "patch", "head", "options", "websocket", "api_route"}


def _is_route(dec) -> bool:
    node = dec.func if isinstance(dec, ast.Call) else dec
    return isinstance(node, ast.Attribute) and node.attr.lower() in _HTTP and isinstance(dec, ast.Call)


def build(code: str) -> dict:
    """{"functions": {name: {start, end, public, entry, callers, calls, referenced}}, "main_calls": [...]}"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"functions": {}, "main_calls": []}
    defs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    info = {name: {"start": n.lineno, "end": getattr(n, "end_lineno", n.lineno), "public": not name.startswith("_"),
                   "entry": None, "callers": [], "calls": [], "referenced": False} for name, n in defs.items()}
    for name, n in defs.items():
        if any(_is_route(d) for d in n.decorator_list):
            info[name]["entry"] = "http"
        elif n.decorator_list:
            info[name]["entry"] = "decorated"          # a framework hook, a task, a command: someone else calls it
    main_calls: list = []
    for n in tree.body:
        if isinstance(n, ast.If) and "__name__" in ast.dump(n.test) and "__main__" in ast.dump(n.test):
            for c in ast.walk(n):
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in defs:
                    main_calls.append(c.func.id)
                    info[c.func.id]["entry"] = info[c.func.id]["entry"] or "main"
    for caller, node in defs.items():
        for c in ast.walk(node):
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in defs and c.func.id != caller:
                info[c.func.id]["callers"].append(caller)
                info[caller]["calls"].append(c.func.id)
    # any other mention (callback, dict of handlers, __all__) keeps a function alive
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in defs and isinstance(node.ctx, ast.Load):
            info[node.id]["referenced"] = True
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in defs:
            info[node.value]["referenced"] = True
    for name, i in info.items():
        i["callers"] = sorted(set(i["callers"]))
        i["calls"] = sorted(set(i["calls"]))
        if i["entry"] is None and i["public"]:
            i["entry"] = "public"
    return {"functions": info, "main_calls": sorted(set(main_calls))}


def function_at(graph: dict, line: int) -> str | None:
    best = None
    for name, i in graph.get("functions", {}).items():
        if i["start"] <= line <= i["end"] and (best is None or i["start"] >= graph["functions"][best]["start"]):
            best = name
    return best


def reaches(graph: dict, name: str, _seen=None) -> str | None:
    """The entry point kind through which ``name`` can be reached ('http', 'main', 'public', ...), or None."""
    fns = graph.get("functions", {})
    if name not in fns:
        return None
    seen = _seen or set()
    if name in seen:
        return None
    seen.add(name)
    i = fns[name]
    if i["entry"]:
        return i["entry"]
    if i["referenced"] and not i["callers"]:
        return "referenced"
    for c in i["callers"]:
        r = reaches(graph, c, seen)
        if r:
            return r
    return None
