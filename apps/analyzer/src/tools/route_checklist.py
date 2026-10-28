# -*- coding: utf-8 -*-
"""Route-by-route checklist (deterministic, no LLM, nothing is executed).

A free-form review misses things nobody wrote down. This module walks every HTTP
handler it can find and answers the same questions for each one:

    auth        does the handler (or the whole app) check who is calling?
    writes      does it change state (INSERT/UPDATE/DELETE, files)?
    check-act   does it read a value, decide on it, then write without a guard (race)?
    rowcount    does it ever look at how many rows an UPDATE/DELETE touched?
    bounds      does a client-supplied amount / size get a range check?
    json        is the request body indexed without validation (KeyError -> 500)?

The answers become findings (same shape as ``static_scan`` findings) plus a table
(``routes``) so the report can show that *every* route was examined, not just the ones
that produced a finding. Python (Flask / FastAPI / Blueprint) uses the AST; Express uses
a conservative line check. Heuristics: a finding means "look here", not "proven".
"""
from __future__ import annotations

import ast
import re

_HTTP = {"get", "post", "put", "delete", "patch", "route"}
_WRITE_VERBS = ("insert", "update", "delete", "replace", "drop", "alter")
_MONEY = re.compile(r"balance|amount|price|payment|transfer|credit|debit|wallet|refund|invoice|order", re.I)
_AMOUNT_KEYS = ("amount", "price", "qty", "quantity", "count", "total", "sum", "size", "limit")

_PUBLIC_PATH = re.compile(r"^/?(login|logout|signin|signup|register|health|healthz|ping|status|docs|redoc|openapi\.json|metrics|favicon\.ico|static.*)?/?$", re.I)
_AUTH_DECORATOR = re.compile(r"login_required|auth|jwt|token_required|requires|permission|protect|role|roles_|secured|authorized", re.I)
_AUTH_BODY = re.compile(
    r"current_user|\bg\.user\b|session\s*\[|session\.get\(|Authorization|abort\(\s*40[13]\b|"
    r"verify_\w+|check_token|decode_token|get_jwt|request\.authorization|"
    r"HTTPException\(\s*status_code\s*=\s*40[13]|raise\s+Unauthorized|raise\s+Forbidden",
)
# a handler that reads a credential header itself (X-Api-Key, X-Signature, ...) does its own auth check
_AUTH_HEADER = re.compile(r"headers(?:\.get\(|\s*\[)\s*['\"][^'\"]*(?:key|token|auth|secret|signature)[^'\"]*['\"]", re.I)
_SENSITIVE = re.compile(r"\busers?\b|\baccounts?\b|e-?mail|passw|secret|send_file|send_from_directory", re.I)
_TXN = re.compile(r"BEGIN\b|\.begin\(|transaction|atomic|FOR\s+UPDATE|with_for_update|isolation", re.I)
_GUARD_SQL = re.compile(r"\bAND\b[^;]*?(>=|<=|>|<|!=)|\bWHERE\b[^;]*?(>=|<=)", re.I)
_RANGE = re.compile(r"[<>]=?\s*0\b|\b0\s*[<>]=?|\bmax\s*\(|\bmin\s*\(|\babs\s*\(|isinstance\s*\(|\bclamp\w*\s*\(|\bge\s*=|\bgt\s*=|\ble\s*=")


def _finding(rid, title, sev, cwe, line, snippet, fix, kind="logic"):
    return {"id": rid, "title": title, "severity": sev, "cwe": cwe, "kind": kind,
            "line": line, "snippet": snippet.strip()[:160], "fix": fix, "source": "route-checklist"}


def _dec_name(dec: ast.AST) -> str:
    node = dec.func if isinstance(dec, ast.Call) else dec
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _is_route_dec(dec) -> bool:
    return (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
            and dec.func.attr.lower() in _HTTP and bool(dec.args))


def _route_decorator(fn):
    """Return (path, methods) when ``fn`` is an HTTP handler, else None."""
    for dec in fn.decorator_list:
        if not _is_route_dec(dec):
            continue
        attr = dec.func.attr.lower()
        first = dec.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        methods = [attr.upper()] if attr != "route" else ["GET"]
        for kw in dec.keywords:
            if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                methods = [e.value.upper() for e in kw.value.elts
                           if isinstance(e, ast.Constant) and isinstance(e.value, str)] or methods
        return first.value, methods
    return None


def _sql_text(node: ast.AST) -> str:
    """Literal part of a SQL argument (constant, f-string or a + b)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(node, ast.BinOp):
        return _sql_text(node.left) + _sql_text(node.right)
    return ""


def _executes(fn):
    """[(lineno, sql_literal)] for every .execute()/.executemany() call, in source order."""
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr in ("execute", "executemany", "executescript") and n.args:
            out.append((n.lineno, _sql_text(n.args[0])))
    return sorted(out)


def _verb(sql: str) -> str:
    m = re.match(r"\s*(\w+)", sql or "")
    return m.group(1).lower() if m else ""


def _global_auth(tree: ast.AST) -> bool:
    """A before_request hook or app-wide dependency that looks like an auth check."""
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in n.decorator_list:
                if _dec_name(dec).endswith(("before_request", "before_app_request")):
                    body_src = ast.unparse(n)
                    if _AUTH_BODY.search(body_src) or re.search(r"token|auth|jwt|api[_-]?key", body_src, re.I):
                        return True
        if isinstance(n, ast.Call) and _dec_name(n.func) in ("FastAPI", "APIRouter"):
            for kw in n.keywords:
                if kw.arg == "dependencies" and re.search(r"auth|token|user|jwt", ast.unparse(kw.value), re.I):
                    return True
    return False


def _has_auth(fn, global_auth: bool) -> bool:
    if global_auth:
        return True
    if any(_AUTH_DECORATOR.search(_dec_name(d)) for d in fn.decorator_list if not _is_route_dec(d)):
        return True
    for default in list(fn.args.defaults) + list(fn.args.kw_defaults):
        if default is not None and re.search(r"Depends\s*\(.*(user|auth|token|jwt|current)", ast.unparse(default), re.I):
            return True
    body = ast.unparse(fn)
    return bool(_AUTH_BODY.search(body) or _AUTH_HEADER.search(body))


def _check_then_act(fn, execs) -> int:
    """Line of a write that follows a SELECT + an ``if`` decision, with no guard; else 0."""
    select_line = next((ln for ln, sql in execs if _verb(sql) == "select"), 0)
    if not select_line:
        return 0
    for ln, sql in execs:
        if ln > select_line and _verb(sql) in _WRITE_VERBS and not _GUARD_SQL.search(sql):
            if any(isinstance(n, ast.If) and select_line < n.lineno < ln for n in ast.walk(fn)):
                return ln
    return 0


def _amount_access(fn):
    """[(lineno, key)] where a client-supplied amount-like key is read."""
    hits = []
    for n in ast.walk(fn):
        key = None
        if isinstance(n, ast.Subscript):
            sl = n.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                key = sl.value
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get" and n.args:
            a = n.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                key = a.value
        if key and key.lower() in _AMOUNT_KEYS:
            hits.append((n.lineno, key))
    return sorted(hits)


def _reads_request_body(fn) -> bool:
    return bool(re.search(r"request\.(get_json|json)\b", ast.unparse(fn)))


def _bare_json_index(fn) -> int:
    """Line where a key of the JSON body is indexed with [] and nothing validates the body."""
    src = ast.unparse(fn)
    if not _reads_request_body(fn):
        return 0
    if re.search(r"\.get\(|try:|except\b|validate|schema|pydantic|BaseModel|abort\(\s*400|\bif\s+not\s+data", src):
        return 0
    for n in sorted((x for x in ast.walk(fn) if isinstance(x, ast.Subscript)), key=lambda x: x.lineno):
        if isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
            if isinstance(n.value, ast.Name) and n.value.id in ("data", "body", "payload", "j", "req"):
                return n.lineno
    return 0


def _python_routes(code: str):
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return [], []
    lines = code.splitlines()

    def at(line):
        return lines[line - 1] if 0 < line <= len(lines) else ""

    glob_auth = _global_auth(tree)
    findings, table = [], []
    handlers = sorted((n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))),
                      key=lambda n: n.lineno)
    for fn in handlers:
        info = _route_decorator(fn)
        if not info:
            continue
        path, methods = info
        src = ast.unparse(fn)
        execs = _executes(fn)
        writes = [(ln, s) for ln, s in execs if _verb(s) in _WRITE_VERBS]
        state_changing = bool(writes) or any(m in ("POST", "PUT", "PATCH", "DELETE") for m in methods)
        authed = _has_auth(fn, glob_auth)
        public = bool(_PUBLIC_PATH.match(path)) or fn.name in ("login", "logout", "register", "signup", "health")
        money = bool(_MONEY.search(src)) or any(_MONEY.search(s) for _, s in execs)
        cta_line = _check_then_act(fn, execs)
        has_txn = bool(_TXN.search(src))
        reads_rowcount = "rowcount" in src
        amounts = _amount_access(fn)
        ranged = bool(_RANGE.search(src))
        json_line = _bare_json_index(fn)

        table.append({
            "route": path, "methods": methods, "function": fn.name, "line": fn.lineno,
            "auth": "yes" if authed else ("public" if public else "no"),
            "writes": bool(writes), "check_then_act": bool(cta_line) and not has_txn,
            "rowcount_checked": reads_rowcount, "bounds_checked": ranged if amounts else None,
        })

        sensitive_read = bool(_SENSITIVE.search(src)) or any(_SENSITIVE.search(s) for _, s in execs)
        if not authed and not public and (state_changing or money or sensitive_read):
            findings.append(_finding(
                "route-no-auth", f"{methods[0]} {path}: no authentication or authorization check",
                "high" if (state_changing or money) else "medium", "CWE-862",
                fn.lineno, at(fn.lineno),
                "Require an authenticated caller on this route and check that the caller owns the resource "
                "(decorator, dependency or a global before_request hook).", kind="security"))
        if cta_line and not has_txn:
            findings.append(_finding(
                "route-check-then-act", f"{methods[0]} {path}: value is read, checked, then written without a guard (race)",
                "high" if money else "medium", "CWE-367", cta_line, at(cta_line),
                "Do the check inside the write: UPDATE ... SET balance = balance - ? WHERE id = ? AND balance >= ?, "
                "check cursor.rowcount, and wrap it in one transaction (BEGIN IMMEDIATE)."))
        if writes and not reads_rowcount:
            ln, _ = next((w for w in writes if _verb(w[1]) in ("update", "delete")), (0, ""))
            if ln:
                findings.append(_finding(
                    "route-unchecked-rowcount", f"{methods[0]} {path}: UPDATE/DELETE result is never checked",
                    "medium" if money else "low", "CWE-252", ln, at(ln),
                    "Check cursor.rowcount after UPDATE/DELETE: 0 rows means the target does not exist "
                    "(for a transfer, money would leave one account and arrive nowhere)."))
        if amounts and not ranged:
            ln, key = amounts[0]
            findings.append(_finding(
                "route-amount-no-bounds", f"{methods[0]} {path}: client value '{key}' is used without a range check",
                "high" if (money and key.lower() in ("amount", "price", "total", "sum")) else "medium", "CWE-20",
                ln, at(ln),
                "Validate type and range on the server: integer (or Decimal), > 0, and below a sane maximum. "
                "A negative amount reverses a transfer."))
        if json_line:
            findings.append(_finding(
                "route-unvalidated-json", f"{methods[0]} {path}: request body is indexed without validation",
                "low", "CWE-20", json_line, at(json_line),
                "Validate the body (schema / pydantic) and answer 400 for a missing or wrong-typed key instead of 500."))
    return findings, table


_PARAM_AMOUNTS = ("amount", "price", "qty", "quantity", "total", "sum", "delta", "value")


def _read_modify_write(execs) -> int:
    """Line of an UPDATE that stores a Python-side value into a column an earlier SELECT read.

    ``SELECT balance`` ... ``UPDATE users SET balance = ?`` loses concurrent updates (lost update);
    ``SET balance = balance + ?`` does not, so that form is left alone.
    """
    read_cols = {}
    for ln, sql in execs:
        if _verb(sql) == "select":
            m = re.match(r"\s*select\s+(.*?)\s+from\b", sql, re.I | re.S)
            if m:
                for col in re.split(r"\s*,\s*", m.group(1)):
                    read_cols.setdefault(col.strip().lower(), ln)
        elif _verb(sql) == "update":
            m = re.search(r"\bset\s+(\w+)\s*=\s*(\?|%s|:\w+|\{)", sql, re.I)
            if m and read_cols.get(m.group(1).lower(), ln + 1) < ln and not _TXN.search(sql):
                return ln
    return 0


def _python_functions(code: str):
    """Checks for plain functions that run SQL (service / DAO modules with no HTTP handlers)."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return []
    lines = code.splitlines()

    def at(line):
        return lines[line - 1] if 0 < line <= len(lines) else ""

    scopes = [tree.body]
    scopes += [n.body for n in tree.body if isinstance(n, ast.ClassDef)]
    out = []
    for body in scopes:
        for fn in body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or _route_decorator(fn):
                continue
            execs = _executes(fn)
            if not execs:
                continue
            src = ast.unparse(fn)
            writes = [(ln, s_) for ln, s_ in execs if _verb(s_) in _WRITE_VERBS]
            money = bool(_MONEY.search(fn.name)) or any(_MONEY.search(s_) for _, s_ in execs)
            has_txn = bool(_TXN.search(src))
            params = [a.arg for a in list(fn.args.args) + list(fn.args.kwonlyargs)]

            cta = _check_then_act(fn, execs)
            if cta and not has_txn:
                out.append(_finding(
                    "func-check-then-act", f"{fn.name}(): value is read, checked, then written without a guard (race)",
                    "high" if money else "medium", "CWE-367", cta, at(cta),
                    "Make the check part of the write: UPDATE ... SET balance = balance - ? WHERE id = ? AND balance >= ?, "
                    "check cursor.rowcount, and run it in one transaction (BEGIN IMMEDIATE)."))
            rmw = _read_modify_write(execs)
            if rmw and not has_txn and rmw != cta:
                out.append(_finding(
                    "func-read-modify-write", f"{fn.name}(): value is read, changed in Python and written back (lost update)",
                    "high" if money else "medium", "CWE-362", rmw, at(rmw),
                    "Let the database do the arithmetic (SET balance = balance + ?) and use a transaction."))
            amounts = [p for p in params if p.lower() in _PARAM_AMOUNTS]
            if amounts and writes and not _RANGE.search(src):
                ln = writes[0][0]
                out.append(_finding(
                    "func-amount-no-bounds", f"{fn.name}(): parameter '{amounts[0]}' is written without a range check",
                    "high" if money else "medium", "CWE-20", ln, at(ln),
                    "Reject non-numeric, NaN, zero and negative values and cap the maximum: a negative amount "
                    "reverses a transfer, a huge one overflows a balance."))
            if writes and "rowcount" not in src:
                ln, _ = next((w for w in writes if _verb(w[1]) in ("update", "delete")), (0, ""))
                if ln:
                    out.append(_finding(
                        "func-unchecked-rowcount", f"{fn.name}(): UPDATE/DELETE result is never checked",
                        "medium" if money else "low", "CWE-252", ln, at(ln),
                        "Check cursor.rowcount: 0 rows means the target does not exist; do not report success."))
    return out


_JS_ROUTE = re.compile(r"""\b(app|router)\.(post|put|patch|delete)\(\s*['"`]([^'"`]+)['"`]""")
_JS_AUTH = re.compile(r"auth|passport|jwt|isLoggedIn|ensureLoggedIn|requireUser|verifyToken|protect|session", re.I)


def _js_routes(code: str):
    findings, table = [], []
    global_auth = bool(re.search(r"\b(app|router)\.use\([^)]*(auth|passport|jwt|session|verifyToken)", code, re.I))
    for i, line in enumerate(code.splitlines(), start=1):
        m = _JS_ROUTE.search(line)
        if not m:
            continue
        method, path = m.group(2).upper(), m.group(3)
        authed = global_auth or bool(_JS_AUTH.search(line))
        public = bool(_PUBLIC_PATH.match(path))
        table.append({"route": path, "methods": [method], "function": "", "line": i,
                      "auth": "yes" if authed else ("public" if public else "no"),
                      "writes": True, "check_then_act": False, "rowcount_checked": None, "bounds_checked": None})
        if not authed and not public:
            findings.append(_finding(
                "route-no-auth", f"{method} {path}: no authentication middleware on this route", "high", "CWE-862",
                i, line, "Add an auth middleware to the route or app.use() it for the whole router "
                "(line-based check: middleware defined elsewhere may be missed).", kind="security"))
    return findings, table


def checklist(code: str, language: str) -> dict:
    """Return {"findings": [...], "routes": [...]} for the submitted text."""
    try:
        if language == "python":
            findings, table = _python_routes(code)
            findings = findings + _python_functions(code)
        elif language in ("javascript", "typescript"):
            findings, table = _js_routes(code)
        else:
            findings, table = [], []
    except Exception:  # a checklist bug must never kill a scan
        findings, table = [], []
    return {"findings": findings, "routes": table}


def render_routes_md(routes: list) -> str:
    """Compact table: proof that every route was examined."""
    if not routes:
        return ""
    out = ["### Route checklist", "",
           "| Route | Auth | Writes | Check-then-act | Rowcount | Bounds |", "|---|---|---|---|---|---|"]

    def yn(v):
        return "n/a" if v is None else ("yes" if v else "no")
    for r in routes:
        out.append(f"| {'/'.join(r['methods'])} {r['route']} (line {r['line']}) | {r['auth']} | {yn(r['writes'])} | "
                   f"{'RISK' if r['check_then_act'] else 'ok'} | {yn(r['rowcount_checked'])} | {yn(r['bounds_checked'])} |")
    out.append("")
    return "\n".join(out)
