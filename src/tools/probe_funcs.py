# -*- coding: utf-8 -*-
"""Function probes: prove a bug in a plain (non-HTTP) function by running it and checking an INVARIANT.

    hypothesis  = {function, kind, args, setup rows, [interleaved writer], checks}   (data, not code)
    sandbox     = src/tools/proof_funcs_harness.py inside the same containment as proof.py
    verdict     = CONFIRMED when the invariant is violated, NOT_REPRODUCED when it holds

Hypotheses come from two places, merged and validated the same way:
  * ``generate(code)``      deterministic templates read from the AST (money parameters, id parameters, SQL
                            statements, comparisons against literals). No model, no network.
  * ``llm_hypotheses(...)`` a model proposes more, in the same structure; anything that is not one of the
                            known check types or touches a function that does not exist is dropped.
A model never writes executable test code here: it fills in a declarative spec, so what runs is bounded.

Honest limits: sqlite3 only; a "race" is a deterministic interleaving (another writer's UPDATE is injected
between the function's read and its write), which proves the window exists, not how often it is hit.
"""
from __future__ import annotations

import ast
import json
import re

PAYLOAD = "VSHPQ' OR '1'='1"
NUM_PAYLOAD = "999 OR 1=1"
CMD_PAYLOAD = "VSHPQ; echo pwned"
MISSING_ID = 999
MAX_HYPOTHESES = 48
NAN = {"$float": "nan"}

CHECK_TYPES = {"db_unchanged", "sql_equals", "sql_min", "no_exception", "rejects", "payload_in_sql",
               "payload_in_cmd", "no_success_without_effect", "no_lost_update"}

_AMOUNT = re.compile(r"(?i)^(amount|sum|total|price|qty|quantity|delta|cost|fee|value|\w+_(amount|total|price|qty|sum|fee))$")
_ID = re.compile(r"(?i)^(id|uid|\w+_id|(\w+_)?(user|account|acct|customer|owner|sender|recipient|receiver)s?(_\w+)?)$")
_CRED = re.compile(r"(?i)token|secret|passw|pwd|key|credential|auth|code|pin")
_DICTY = re.compile(r"(?i)^(request|req|data|payload|body|params|form)$")
_MONEYCOL = re.compile(r"(?i)balance|amount|total|price|credit|funds|points|stock|quantity|qty|count|limit|uses|left|remaining|quota|attempts|seats")
_CMD_FUNCS = {"os.system", "os.popen", "subprocess.run", "subprocess.call", "subprocess.check_output",
              "subprocess.check_call", "subprocess.Popen"}

# rule id (static_scan / route_checklist) -> hypothesis kinds that can prove it
KINDS_FOR = {
    "sqli-fstring": ("sqli", "sqli_data"), "sqli-concat": ("sqli", "sqli_data"), "sqli-format": ("sqli", "sqli_data"),
    "sqli-percent": ("sqli", "sqli_data"),
    "cmd-injection-py": ("cmdi",), "shell-true": ("cmdi",), "taint-flow": ("sqli", "sqli_data", "cmdi"),
    "func-amount-no-bounds": ("negative_amount", "nan_amount", "overdraw"),
    "func-check-then-act": ("race_overdraft", "lost_update"),
    "func-read-modify-write": ("lost_update",),
    "func-unchecked-rowcount": ("missing_target",),
    "logic-fetchone-index": ("missing_row",),
}

# kind -> (title prefix, severity, cwe, finding kind) for findings that no rule reported but a probe proved
NEW_FINDING = {
    "negative_amount": ("A negative amount is accepted and changes stored data", "high", "CWE-20", "logic"),
    "nan_amount": ("NaN/inf is accepted as an amount and changes stored data", "high", "CWE-20", "logic"),
    "overdraw": ("An amount larger than the balance drives it below zero", "high", "CWE-840", "logic"),
    "race_overdraft": ("Check-then-act race: the balance can go below zero", "high", "CWE-362", "logic"),
    "lost_update": ("Lost update: a concurrent write is overwritten", "high", "CWE-362", "logic"),
    "transfer_to_missing": ("Money leaves the sender and arrives nowhere (missing recipient)", "high", "CWE-754", "logic"),
    "missing_target": ("Success is reported although no row was affected", "medium", "CWE-754", "logic"),
    "missing_row": ("Crash on a missing row (result is used without a None check)", "medium", "CWE-476", "logic"),
    "sqli": ("SQL injection: input becomes part of the statement", "high", "CWE-89", "security"),
    "sqli_data": ("SQL injection changes data beyond the intended row", "critical", "CWE-89", "security"),
    "cmdi": ("Command injection: input becomes part of a shell command", "critical", "CWE-78", "security"),
    "hardcoded_credential": ("A credential written in the source authenticates the caller", "high", "CWE-798", "security"),
}


# ---- reading the code -----------------------------------------------------------------------------------

def _root(node):
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
        node = node.value if not isinstance(node, ast.Call) else node.func
    return node.id if isinstance(node, ast.Name) else None


def _dotted(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _text(node, env):
    """Text of a string expression with ``{name}`` where a variable is interpolated; (text, [names]) or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, []
    if isinstance(node, ast.JoinedStr):
        out, names = "", []
        for p in node.values:
            if isinstance(p, ast.Constant):
                out += str(p.value)
            elif isinstance(p, ast.FormattedValue):
                n = _root(p.value) or "expr"
                out += "{" + n + "}"
                names.append(n)
        return out, names
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _text(node.left, env), _text(node.right, env)
        if a is not None and b is not None:
            return a[0] + b[0], a[1] + b[1]
        if a is not None:
            n = _root(node.right)
            return (a[0] + "{" + (n or "expr") + "}", a[1] + ([n] if n else []))
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) \
            and isinstance(node.left.value, str):
        elts = node.right.elts if isinstance(node.right, ast.Tuple) else [node.right]
        names = [_root(e) or "expr" for e in elts]
        txt, i = "", 0
        for piece in re.split(r"(%[sd])", node.left.value):
            if piece in ("%s", "%d") and i < len(names):
                txt += "{" + names[i] + "}"
                i += 1
            else:
                txt += piece
        return txt, names
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format" \
            and isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str):
        names = [_root(a) or "expr" for a in node.args] + [_root(k.value) or "expr" for k in node.keywords]
        txt, i = "", 0
        for piece in re.split(r"(\{[^}]*\})", node.func.value.value):
            if re.fullmatch(r"\{[^}]*\}", piece) and names:
                txt += "{" + names[min(i, len(names) - 1)] + "}"
                i += 1
            else:
                txt += piece
        return txt, names
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _function_info(fn: ast.FunctionDef) -> dict:
    params = []
    args = fn.args
    pos = args.posonlyargs + args.args
    defaults = [None] * (len(pos) - len(args.defaults)) + list(args.defaults)
    for a, d in zip(pos, defaults):
        params.append((a.arg, d.value if isinstance(d, ast.Constant) else (None if d is None else ...)))
    pnames = {p for p, _ in params}
    env: dict = {}
    for node in sorted((n for n in ast.walk(fn) if isinstance(n, ast.Assign)), key=lambda n: n.lineno):
        t = _text(node.value, env)
        if t is not None:
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    env[tgt.id] = t
    sqls, cmds, literals = [], [], []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("execute", "executemany") \
                and node.args:
            t = _text(node.args[0], env)
            if t is None:
                continue
            text = _norm(t[0])
            kind = (text.split(" ", 1)[0].lower() if text else "")
            bound = []
            if len(node.args) > 1 and isinstance(node.args[1], (ast.Tuple, ast.List)):
                bound = [_root(e) for e in node.args[1].elts]
            sqls.append({"kind": kind if kind in ("select", "insert", "update", "delete", "replace") else "other",
                         "text": text, "interp": [n for n in t[1] if n in pnames], "bound": [b for b in bound if b],
                         "line": node.lineno})
        elif isinstance(node, ast.Call) and _dotted(node.func) in _CMD_FUNCS and node.args:
            shell = _dotted(node.func).startswith("os.") or any(
                k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords)
            t = _text(node.args[0], env)
            if t is not None and shell:
                cmds.append({"text": t[0], "interp": [n for n in t[1] if n in pnames], "line": node.lineno})
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
            a, b = node.left, node.comparators[0]
            for x, y in ((a, b), (b, a)):
                if isinstance(x, ast.Name) and x.id in pnames and isinstance(y, ast.Constant) \
                        and isinstance(y.value, str) and len(y.value) >= 4 and _CRED.search(x.id):
                    literals.append((x.id, y.value, node.lineno))
    sqls.sort(key=lambda s: s["line"])
    return {"name": fn.name, "params": params, "start": fn.lineno, "end": getattr(fn, "end_lineno", fn.lineno),
            "sqls": sqls, "cmds": cmds, "literals": literals}


def functions(code: str) -> list:
    """Public, undecorated, top-level functions with their parameters, SQL statements and shell commands."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [_function_info(n) for n in tree.body
            if isinstance(n, ast.FunctionDef) and not n.name.startswith("_") and not n.decorator_list]


# ---- schema and fixture rows ----------------------------------------------------------------------------

def _cols_in(segment: str) -> list:
    seg = re.sub(r"\{[^}]*\}", "?", segment)
    return [c for c in re.findall(r"([A-Za-z_]\w*)\s*(?:=|<>|!=|>=|<=|<|>|\bIN\b|\bLIKE\b)", seg, re.I)
            if c.lower() not in ("and", "or", "not", "where", "set")]


def infer_schema(code: str, infos: list | None = None) -> dict:
    """{table: {"cols": [...], "seed": bool}} from the SQL the module executes; code's own CREATE TABLE wins."""
    infos = infos if infos is not None else functions(code)
    tables: dict = {}

    def tbl(n):
        return tables.setdefault(n.lower(), {"cols": [], "seed": False})

    def add(t, c):
        if c and c.lower() not in ("select", "from", "where") and c not in t["cols"]:
            t["cols"].append(c)

    for fi in infos:
        for s in fi["sqls"]:
            t = s["text"]
            if (m := re.match(r"insert\s+(?:or\s+\w+\s+)?into\s+(\w+)\s*\(([^)]*)\)", t, re.I)):
                for c in m.group(2).split(","):
                    add(tbl(m.group(1)), c.strip().strip('"`[]'))
            elif (m := re.match(r"update\s+(\w+)\s+set\s+(.*?)(?:\s+where\s+(.*))?$", t, re.I)):
                tb = tbl(m.group(1))
                tb["seed"] = True
                for c in _cols_in(m.group(2)) + _cols_in(m.group(3) or ""):
                    add(tb, c)
            elif (m := re.match(r"delete\s+from\s+(\w+)(?:\s+where\s+(.*))?$", t, re.I)):
                tb = tbl(m.group(1))
                tb["seed"] = True
                for c in _cols_in(m.group(2) or ""):
                    add(tb, c)
            elif (m := re.match(r"select\s+(.*?)\s+from\s+(\w+)(.*)$", t, re.I)):
                tb = tbl(m.group(2))
                tb["seed"] = True
                for c in m.group(1).split(","):
                    c = c.strip()
                    if re.fullmatch(r"[A-Za-z_]\w*", c):
                        add(tb, c)
                wm = re.search(r"\bwhere\b(.*)", m.group(3), re.I)
                for c in _cols_in(wm.group(1) if wm else ""):
                    add(tb, c)
    return tables


def _own_ddl(code: str) -> list:
    out = []
    try:
        for n in ast.walk(ast.parse(code)):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and re.search(r"create\s+table", n.value, re.I):
                for stmt in n.value.split(";"):
                    if re.match(r"\s*create\s+table", stmt, re.I):
                        out.append(re.sub(r"(?i)^\s*create\s+table\s+(?!if\s+not\s+exists)", "CREATE TABLE IF NOT EXISTS ", stmt.strip()))
    except SyntaxError:
        pass
    return out


def schema_sql(code: str, schema: dict) -> list:
    own = _own_ddl(code)
    have = {m.group(1).lower() for s in own if (m := re.match(r"create table if not exists\s+[\"`]?(\w+)", s, re.I))}
    out = list(own)
    for name, t in schema.items():
        if name in have:
            continue
        cols = ['"id" INTEGER PRIMARY KEY'] if "id" in [c.lower() for c in t["cols"]] else []
        cols += [f'"{c}"' for c in t["cols"] if c.lower() != "id"]
        out.append(f'CREATE TABLE IF NOT EXISTS "{name}" ({", ".join(cols) or "x"})')
    return out


def _seed_value(col: str, i: int):
    c = col.lower()
    if c == "id" or c.endswith("_id"):
        return i
    if _MONEYCOL.search(c):
        return 100
    if "email" in c:
        return f"user{i}@example.com"
    if re.search(r"pass|token|secret|hash", c):
        return f"pw{i}"
    if re.search(r"expires|date|time|_at$", c):
        return "2999-01-01T00:00:00"
    if re.search(r"role|status", c):
        return "user"
    return f"user{i}" if re.search(r"name|title", c) else f"v{i}"


def seed_sql(schema: dict) -> list:
    out = []
    for name, t in schema.items():
        if not t["seed"] or not t["cols"]:
            continue
        cols = t["cols"]
        for i in (1, 2, 3):
            vals = ", ".join(repr(_seed_value(c, i)) for c in cols)
            out.append(f'INSERT INTO "{name}" ({", ".join(chr(34) + c + chr(34) for c in cols)}) VALUES ({vals})')
    return out


# ---- deterministic hypotheses -----------------------------------------------------------------------------

def _benign(fi: dict, overrides: dict | None = None, id_values: dict | None = None) -> list:
    """Positional arguments that are valid for every parameter, with ``overrides`` applied. The k-th id-like
    parameter is account k (1, 2, ...) even when another one is overridden, so two accounts stay two accounts;
    a parameter compared with a literal credential gets that literal so the guarded code is reached."""
    overrides, id_values = overrides or {}, id_values or {}
    literal = {p: lit for p, lit, _ in fi["literals"]}
    out, nth = [], 0
    for name, default in fi["params"]:
        is_id = bool(_ID.match(name))
        nth += is_id
        if name in overrides:
            out.append(overrides[name])
        elif name in id_values:
            out.append(id_values[name])
        elif is_id:
            out.append(nth)
        elif name in literal:
            out.append(literal[name])
        elif _AMOUNT.match(name):
            out.append(10)
        elif _DICTY.match(name):
            out.append({"user_id": 1})
        elif default is not None and default is not ...:
            out.append(default)
        elif re.search(r"(?i)email", name):
            out.append("a@example.com")
        else:
            out.append("x")
    return out


def _sql_literal(v) -> str:
    return str(v) if isinstance(v, (int, float)) else "'" + str(v).replace("'", "''") + "'"


def _id_params(fi):
    return [p for p, _ in fi["params"] if _ID.match(p)]


def _amount_params(fi):
    return [p for p, _ in fi["params"] if _AMOUNT.match(p)]


def _h(fi, kind, suffix, title, invariant, args, checks, **extra):
    h = {"id": f"{fi['name']}:{kind}" + (f":{suffix}" if suffix else ""), "function": fi["name"], "kind": kind,
         "title": f"{fi['name']}(): {title}", "invariant": invariant, "args": args, "checks": checks}
    h.update(extra)
    return h


def generate(code: str) -> dict:
    """{"hypotheses": [...], "schema": [sql...], "tables": {...}}"""
    infos = functions(code)
    tables = infer_schema(code, infos)
    hyps: list = []
    sum_col = {}
    for fi in infos:
        sqls, ids, amounts = fi["sqls"], _id_params(fi), _amount_params(fi)
        writes = [s for s in sqls if s["kind"] in ("insert", "update", "delete", "replace")]
        selects = [s for s in sqls if s["kind"] == "select"]
        if not sqls and not fi["cmds"] and not fi["literals"]:
            continue

        # money / quantity parameter: bad values must be refused, so stored data must not change
        if amounts and writes:
            a = amounts[0]
            hyps.append(_h(fi, "negative_amount", "", f"negative {a}", "a negative amount must be refused: stored data is unchanged",
                           _benign(fi, {a: -5}), [{"type": "db_unchanged"}]))
            hyps.append(_h(fi, "nan_amount", "", f"{a} = NaN", "a non-finite amount must be refused: stored data is unchanged",
                           _benign(fi, {a: NAN}), [{"type": "db_unchanged"}]))

        # an id that does not exist
        sel_ids = [p for s in selects for p in s["bound"] + s["interp"] if p in ids]
        if selects and (sel_ids or ids):
            p = (sel_ids or ids)[0]
            hyps.append(_h(fi, "missing_row", "", f"{p} does not exist", "a missing record must not crash the function",
                           _benign(fi, {p: MISSING_ID}), [{"type": "no_exception"}]))
        wr_ids = [p for s in writes if s["kind"] in ("update", "delete") for p in s["bound"] + s["interp"] if p in ids]
        if wr_ids:
            p = wr_ids[0]
            hyps.append(_h(fi, "missing_target", "", f"{p} does not exist", "success must not be reported when no row was affected",
                           _benign(fi, {p: MISSING_ID}), [{"type": "no_success_without_effect"}]))

        # a transfer: two accounts, money out and money in
        rel_minus = [(m.group(1), m.group(2)) for s in writes if s["kind"] == "update"
                     for m in [re.match(r"update\s+(\w+)\s+set\s+(\w+)\s*=\s*\2\s*-", s["text"], re.I)] if m]
        rel_plus = [(m.group(1), m.group(2)) for s in writes if s["kind"] == "update"
                    for m in [re.match(r"update\s+(\w+)\s+set\s+(\w+)\s*=\s*\2\s*\+", s["text"], re.I)] if m]
        if rel_minus and rel_plus and len(ids) >= 2 and amounts:
            table, col = rel_minus[0]
            hyps.append(_h(fi, "transfer_to_missing", "", f"{ids[1]} does not exist", f"the sum of all {col} values is conserved",
                           _benign(fi, {ids[1]: MISSING_ID}),
                           [{"type": "sql_equals", "sql": f'SELECT SUM("{col}") FROM "{table}"', "expect": 300,
                             "label": f"sum of {table}.{col}"}]))
            sum_col[fi["name"]] = (table, col)

        # an amount larger than what is there: the balance must not go below zero
        for w in writes:
            m = re.match(r"update\s+(\w+)\s+set\s+(\w+)\s*=\s*\2\s*-\s*(?:\?|\{\w+\})\s+where\s+(\w+)\s*=\s*(?:\?|\{\w+\})", w["text"], re.I)
            if not (m and amounts and _MONEYCOL.search(m.group(2))):
                continue
            table, col, wcol = m.groups()
            key = next((p for p in w["bound"] + w["interp"] if p in ids), None)
            ov = {amounts[0]: 1000}
            ov_key = _seed_value(wcol, 1)
            if key:
                ov[key] = ov_key
            hyps.append(_h(fi, "overdraw", "", f"{amounts[0]} larger than the {col}", f"{col} never goes below zero",
                           _benign(fi, ov), [{"type": "sql_min", "sql": f'SELECT "{col}" FROM "{table}" WHERE "{wcol}" = {_sql_literal(ov_key)}',
                                              "min": 0, "label": f"{table}.{col} after taking 1000"}]))
            break

        # read -> decide -> write with another writer in between
        param_names = {n for n, _ in fi["params"]}
        for sel in selects:
            m = re.match(r"select\s+(\w+)\s+from\s+(\w+)\s+where\s+(\w+)\s*=\s*(?:\?|\{\w+\})", sel["text"], re.I)
            if not m:
                continue
            col, table, wcol = m.groups()
            later = [w for w in writes if w["kind"] == "update" and w["line"] > sel["line"]
                     and re.match(rf"update\s+{table}\s+set\s+{col}\s*=", w["text"], re.I)]
            if not later:
                continue
            upd = later[0]["text"]
            relative = re.match(rf"update\s+{table}\s+set\s+{col}\s*=\s*{col}\s*[-+]", upd, re.I)
            key = next((p for p in sel["bound"] + sel["interp"] if p in param_names), None)
            bound = key if key in ids else (ids[0] if ids else None)
            if amounts and bound:
                where = f'"{wcol}" = 1'
                if re.match(rf"update\s+{table}\s+set\s+{col}\s*=\s*{col}\s*-", upd, re.I):
                    hyps.append(_h(fi, "race_overdraft", "", "balance is checked, then written, with another writer in between",
                                   f"{col} never goes below zero",
                                   _benign(fi, {amounts[0]: 80, bound: 1}), [{"type": "sql_min", "sql": f'SELECT "{col}" FROM "{table}" WHERE {where}',
                                                                             "min": 0, "label": f"{table}.{col} of {bound}=1"}],
                                   interleave={"after": f"select {col}", "sql": f'UPDATE "{table}" SET "{col}" = "{col}" - 80 WHERE {where}'}))
                elif not relative:
                    hyps.append(_h(fi, "lost_update", "", "value is read, changed in Python, written back, with another writer in between",
                                   f"both changes to {col} survive",
                                   _benign(fi, {amounts[0]: 10, bound: 1}), [{"type": "sql_equals", "sql": f'SELECT "{col}" FROM "{table}" WHERE {where}',
                                                                             "expect": 160, "label": f"{table}.{col} of {bound}=1 (100 + 10 + 50)"}],
                                   interleave={"after": f"select {col}", "sql": f'UPDATE "{table}" SET "{col}" = "{col}" + 50 WHERE {where}'}))
                    hyps.append(_h(fi, "overdraw", "abs", f"{amounts[0]} = -1000", f"{col} never goes below zero",
                                   _benign(fi, {amounts[0]: -1000, bound: 1}), [{"type": "sql_min", "sql": f'SELECT "{col}" FROM "{table}" WHERE {where}',
                                                                                 "min": 0, "label": f"{table}.{col} of {bound}=1"}]))
            elif key and not relative and not amounts:
                # no amount to steer: let the function change the value alone, then again with a writer in between
                val = _seed_value(wcol, 1)
                where = f'"{wcol}" = {_sql_literal(val)}'
                hyps.append(_h(fi, "lost_update", "", f"'{col}' is read, changed in Python, written back, with another writer in between",
                               f"a change made by another writer between the read and the write is not overwritten",
                               _benign(fi, {key: val}), [{"type": "no_lost_update", "sql": f'SELECT "{col}" FROM "{table}" WHERE {where}',
                                                          "competitor_delta": 50, "label": f"{table}.{col} where {wcol}={val}"}],
                               interleave={"after": f"select {col}", "sql": f'UPDATE "{table}" SET "{col}" = "{col}" + 50 WHERE {where}'}))

        # injection: input travels into the statement text
        done_params = set()
        for s in sqls:
            for p in s["interp"]:
                if p in done_params:
                    continue
                done_params.add(p)
                hyps.append(_h(fi, "sqli", p, f"input '{p}' becomes part of the SQL statement", "input stays data: it never appears inside the statement text",
                               _benign(fi, {p: PAYLOAD}), [{"type": "payload_in_sql", "payload": PAYLOAD}]))
                quoted = re.search(r"['\"]\{" + re.escape(p) + r"\}", s["text"])
                if s["kind"] in ("update", "delete") and not quoted and re.search(r"\bwhere\b", s["text"], re.I):
                    hyps.append(_h(fi, "sqli_data", p, f"'{p} = {NUM_PAYLOAD}' hits more rows than one",
                                   "a record that does not exist must not change any row",
                                   _benign(fi, {p: NUM_PAYLOAD}), [{"type": "db_unchanged"}]))
        for c in fi["cmds"]:
            for p in c["interp"]:
                hyps.append(_h(fi, "cmdi", p, f"input '{p}' becomes part of a shell command", "input stays data: it never appears inside a shell command",
                               _benign(fi, {p: CMD_PAYLOAD}), [{"type": "payload_in_cmd", "payload": CMD_PAYLOAD}]))
        for p, lit, _line in fi["literals"]:
            hyps.append(_h(fi, "hardcoded_credential", p, f"the literal '{lit[:12]}...' from the source is accepted as {p}",
                           "a credential that is written in the source must not authenticate anyone",
                           _benign(fi, {p: lit}), [{"type": "rejects"}]))

    seen, uniq = set(), []
    for h in hyps:
        if h["id"] not in seen:
            seen.add(h["id"])
            uniq.append(h)
    schema = schema_sql(code, tables)
    seed = seed_sql(tables)
    for h in uniq:
        h["setup"] = seed
    return {"hypotheses": uniq[:MAX_HYPOTHESES], "schema": schema, "tables": tables}


# ---- hypotheses from a model ---------------------------------------------------------------------------

def _clean_value(v, depth=0):
    if depth > 3:
        return None
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v if not isinstance(v, str) else v[:200]
    if isinstance(v, dict):
        if set(v) == {"$float"} and str(v["$float"]).lower() in ("nan", "inf", "-inf"):
            return {"$float": str(v["$float"]).lower()}
        return {str(k)[:40]: _clean_value(x, depth + 1) for k, x in list(v.items())[:10]}
    if isinstance(v, list):
        return [_clean_value(x, depth + 1) for x in v[:10]]
    return None


def _one_statement(s, allowed) -> bool:
    s = str(s).strip().rstrip(";")
    return bool(s) and ";" not in s and s.split(None, 1)[0].lower() in allowed and len(s) < 400


def validate(h, known_functions: set) -> dict | None:
    """A model's hypothesis in canonical form, or None. Nothing executable survives: values, one-statement
    SELECT checks, one-statement setup rows, check types from a fixed list."""
    if not isinstance(h, dict) or h.get("function") not in known_functions:
        return None
    checks = []
    for c in (h.get("checks") or [])[:4]:
        if not isinstance(c, dict) or c.get("type") not in CHECK_TYPES:
            return None
        t = c["type"]
        if t in ("sql_equals", "sql_min"):
            if not _one_statement(c.get("sql"), ("select",)):
                return None
            key = "expect" if t == "sql_equals" else "min"
            if not isinstance(c.get(key), (int, float, str)) or isinstance(c.get(key), bool):
                return None
            checks.append({"type": t, "sql": str(c["sql"]).strip().rstrip(";"), key: c[key], "label": str(c.get("label") or "")[:80]})
        elif t == "no_lost_update":
            if not _one_statement(c.get("sql"), ("select",)) or not isinstance(c.get("competitor_delta"), (int, float)) \
                    or isinstance(c.get("competitor_delta"), bool):
                return None
            checks.append({"type": t, "sql": str(c["sql"]).strip().rstrip(";"), "competitor_delta": c["competitor_delta"],
                           "label": str(c.get("label") or "")[:80]})
        elif t in ("payload_in_sql", "payload_in_cmd"):
            if not isinstance(c.get("payload"), str) or not 3 <= len(c["payload"]) <= 80:
                return None
            checks.append({"type": t, "payload": c["payload"]})
        else:
            checks.append({"type": t})
    if not checks:
        return None
    args = _clean_value(h.get("args") or [])
    kwargs = _clean_value(h.get("kwargs") or {})
    if not isinstance(args, list) or not isinstance(kwargs, dict):
        return None
    out = {"id": "LLM:" + re.sub(r"[^\w:.-]", "_", str(h.get("id") or h["function"] + ":" + str(h.get("kind") or "x")))[:60],
           "function": h["function"], "kind": re.sub(r"[^\w]", "_", str(h.get("kind") or "llm"))[:30],
           "title": f"{h['function']}(): " + str(h.get("hypothesis") or h.get("title") or "")[:140],
           "invariant": str(h.get("invariant") or h.get("expected") or "")[:200], "args": args, "kwargs": kwargs,
           "checks": checks}
    setup = h.get("setup")
    if isinstance(setup, list):
        if not all(_one_statement(s, ("insert", "update")) for s in setup[:20]):
            return None
        out["setup"] = [str(s).strip().rstrip(";") for s in setup[:20]]
    il = h.get("interleave")
    if isinstance(il, dict):
        if not _one_statement(il.get("sql"), ("update", "insert", "delete")) or not isinstance(il.get("after"), str):
            return None
        out["interleave"] = {"after": il["after"][:80], "sql": str(il["sql"]).strip().rstrip(";")}
    return out


def llm_hypotheses(code: str, runner, findings: list | None = None, *, base: dict | None = None) -> list:
    """Ask a model for more hypotheses in the declarative form. ``runner(text, context) -> parsed JSON`` is
    injected; any failure returns []. The result is validated, deduplicated against ``base``."""
    base = base or generate(code)
    infos = functions(code)
    names = {fi["name"] for fi in infos}
    ctx = {"tables": {t: v["cols"] for t, v in base.get("tables", {}).items()},
           "functions": [{"name": fi["name"], "params": [p for p, _ in fi["params"]], "lines": [fi["start"], fi["end"]]} for fi in infos][:40],
           "fixture": "tables are created from the SQL in the code and seeded with ids 1..3 (balance-like columns = 100); "
                      "payments-like insert-only tables are empty",
           "already_covered": sorted({h["id"] for h in base.get("hypotheses", [])})[:60],
           "findings": [{"id": f.get("id"), "line": f.get("line"), "title": f.get("title")} for f in (findings or [])[:25]]}
    try:
        parsed = runner(code, ctx)
    except Exception:
        return []
    items = parsed.get("hypotheses") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return []
    seen = {(h["function"], json.dumps(h["args"], sort_keys=True, default=str), h["kind"]) for h in base.get("hypotheses", [])}
    out = []
    for it in items[:30]:
        h = validate(it, names)
        if not h:
            continue
        h.setdefault("setup", seed_sql(base.get("tables", {})))
        key = (h["function"], json.dumps(h["args"], sort_keys=True, default=str), h["kind"])
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


# ---- running and reporting -----------------------------------------------------------------------------

def run(code: str, spec: dict | None = None, *, force: bool = False, timeout: int = 20) -> dict:
    """Run the hypotheses in the sandbox. Returns the harness document ({"results": [...], "error": ...})."""
    from src.tools.proof import _run_harness, HARNESS_FUNCS

    spec = spec if spec is not None else generate(code)
    if not spec.get("hypotheses"):
        return {"framework": "functions", "handlers": 0, "results": [], "notes": [], "error": "no function probes apply"}
    payload = {"schema": spec.get("schema") or [], "hypotheses": spec["hypotheses"]}
    return _run_harness(code, timeout=timeout, force=force, harness=HARNESS_FUNCS, spec=payload)


def annotate(findings: list, doc: dict, *, add_new: bool = True) -> None:
    """Attach probe results to the rule findings they can speak about; add a finding for every CONFIRMED probe
    no rule reported. Findings already settled by the handler harness are left alone."""
    results = doc.get("results") or []
    attached = set()
    for f in findings:
        kinds = KINDS_FOR.get(f.get("id", ""))
        if not kinds or f.get("status") in ("CONFIRMED", "NOT_REPRODUCED"):
            continue
        line = int(f.get("line") or 0)
        mine = [r for r in results if r.get("kind") in kinds and r.get("start", 0) <= line <= r.get("end", 0)]
        if not mine:
            continue
        best = next((r for r in mine if r["status"] == "CONFIRMED"), None) \
            or next((r for r in mine if r["status"] == "NOT_REPRODUCED"), None) or mine[0]
        f["proof"] = {"status": best["status"], "check": best.get("check", ""), "evidence": best["evidence"],
                      "route": best["function"], "invariant": best.get("invariant", ""), "isolation": doc.get("isolation", "")}
        f["status"] = best["status"] if best["status"] in ("CONFIRMED", "NOT_REPRODUCED") else "UNCONFIRMED"
        for r in mine:
            if r["status"] == "CONFIRMED":
                attached.add((r["function"], r["kind"]))
    if not add_new:
        return
    for r in results:
        if r.get("status") != "CONFIRMED" or (r["function"], r["kind"]) in attached:
            continue
        title, sev, cwe, kind = NEW_FINDING.get(r["kind"], (r.get("title") or "Invariant violated", "medium", "", "logic"))
        # a rule already reported this function for this kind of defect: the probe supplies the proof, not a duplicate
        if any((f.get("id") in KINDS_FOR and r["kind"] in KINDS_FOR[f["id"]]) and f.get("proof", {}).get("route") == r["function"]
               for f in findings):
            continue
        findings.append({"id": f"probe-{r['kind']}", "title": f"{r['function']}(): {title}", "severity": sev, "cwe": cwe,
                         "kind": kind, "line": r.get("start", 0), "snippet": "", "source": "probe",
                         "fix": r.get("invariant", ""), "status": "CONFIRMED",
                         "proof": {"status": "CONFIRMED", "check": r.get("check", ""), "evidence": r["evidence"],
                                   "route": r["function"], "invariant": r.get("invariant", ""),
                                   "isolation": doc.get("isolation", "")}})
        attached.add((r["function"], r["kind"]))


def prove_functions(code: str, findings: list | None = None, *, runner=None, force: bool = False, timeout: int = 20) -> dict:
    """generate -> (model adds) -> run -> annotate. ``runner`` is optional: without it nothing leaves the machine."""
    spec = generate(code)
    if runner is not None:
        spec["hypotheses"] = (spec["hypotheses"] + llm_hypotheses(code, runner, findings, base=spec))[:MAX_HYPOTHESES + 16]
    doc = run(code, spec, force=force, timeout=timeout)
    if findings is not None and not doc.get("error"):
        annotate(findings, doc)
    return doc
