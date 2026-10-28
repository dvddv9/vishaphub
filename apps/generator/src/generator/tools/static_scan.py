"""Built-in static rules over the generated code: no model, no external program.

The analog of Vishap's `tools/static_scan.py`: a table of rules, each with its CWE and OWASP
category, and the AST checks behind them. Verify runs a rule when the spec lists the matching
`must_never` id (for example `sql-from-input`); a rule that finds something fails that requirement.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str          # the must_never id in the spec
    cwe: str
    owasp: str
    title: str


RULES: dict[str, Rule] = {
    "sql-from-input": Rule("sql-from-input", "CWE-89", "A03:2021 Injection",
                           "SQL text built from a string instead of parameters"),
    "log-raw-input": Rule("log-raw-input", "CWE-532", "A09:2021 Security Logging and Monitoring Failures",
                          "Request data written to a log"),
}


SQL_CALLS = {"execute", "executemany", "executescript", "raw", "text"}
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}


def _assignments(tree: ast.AST) -> dict[str, list[ast.AST]]:
    out: dict[str, list[ast.AST]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.setdefault(t.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            out.setdefault(node.target.id, []).append(node.value)
    return out


def sql_findings(tree: ast.AST) -> list[str]:
    assigns = _assignments(tree)

    def built(expr, depth=0):
        if isinstance(expr, ast.JoinedStr):
            return "an f-string"
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, (ast.Mod, ast.Add)):
            return "% or +"
        if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute)
                and expr.func.attr in ("format", "join")):
            return f".{expr.func.attr}()"
        if isinstance(expr, ast.Name) and depth < 3:
            for value in assigns.get(expr.id, []):
                why = built(value, depth + 1)
                if why:
                    return f"{why} (through {expr.id})"
        return None

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args:
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name in SQL_CALLS:
                why = built(node.args[0])
                if why:
                    found.append(f"line {node.lineno}: {name}() gets SQL built with {why}")
    return found


# Names that carry request data: Flask `request`, WSGI `environ`.
REQUEST_NAMES = {"request", "environ"}


def log_findings(tree: ast.AST) -> list[str]:
    assigns = _assignments(tree)

    def mentions(expr, tainted):
        return any(isinstance(n, ast.Name) and (n.id in REQUEST_NAMES or n.id in tainted)
                   for n in ast.walk(expr))

    tainted: set[str] = set()
    for _ in range(4):
        for name, values in assigns.items():
            if any(mentions(v, tainted) for v in values):
                tainted.add(name)

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        is_print = isinstance(f, ast.Name) and f.id == "print"
        is_log = (isinstance(f, ast.Attribute) and f.attr in LOG_METHODS
                  and "log" in ast.unparse(f.value).lower())
        if not (is_print or is_log):
            continue
        args = list(node.args) + [k.value for k in node.keywords]
        if any(mentions(a, tainted) for a in args):
            found.append(f"line {node.lineno}: {ast.unparse(f)}() gets request data")
    return found


CHECKS: dict[str, Callable[[ast.AST], list[str]]] = {
    "sql-from-input": sql_findings,
    "log-raw-input": log_findings,
}


def scan_code(rule_id: str, trees: dict[str, ast.AST]) -> list[str]:
    """Findings of one rule over parsed files, each prefixed with the file path."""
    check = CHECKS.get(rule_id)
    if check is None:
        return []
    return [f"{path} {finding}" for path, tree in trees.items() for finding in check(tree)]


def rule_for(rule_id: str) -> Rule | None:
    return RULES.get(rule_id)
