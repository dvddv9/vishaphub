# -*- coding: utf-8 -*-
"""Runs INSIDE the function-probe subprocess (see probe_funcs.py). stdlib only, no imports from src.

Where proof_harness.py calls HTTP handlers, this one calls plain functions and judges the result by an
INVARIANT, not by a pattern:

    transfer_funds(1, 2, -5)      invariant: stored data is unchanged (a bad amount must be refused)
    transfer_funds(1, 999, 10)    invariant: the sum of all balances is conserved
    update_balance(1, 10) while another writer adds 50 between its read and its write
                                  invariant: the balance ends at 100 + 10 + 50 (no lost update)

The module is loaded with a REAL in-memory sqlite3 database (schema and rows come from the host) behind a
recording proxy; files, processes and the network are replaced by recorders. A hypothesis is CONFIRMED when
its invariant is violated, NOT_REPRODUCED when it holds, INCONCLUSIVE when the probe itself could not run.

Spec (JSON, argv[2]):  {"schema": [sql...], "hypotheses": [{id, function, kind, title, invariant, setup: [sql],
args: [...], kwargs: {...}, interleave: {after, sql}, checks: [{type, ...}]}]}
A float that JSON cannot carry is written {"$float": "nan"|"inf"|"-inf"}.

Usage:  python -I proof_funcs_harness.py <target.py> <spec.json>   ->  last stdout line is a JSON document.
"""
import ast
import builtins
import contextlib
import importlib.abc
import importlib.machinery
import inspect
import io
import json
import math
import os
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import types

_connect = sqlite3.connect
_real_open = builtins.open
CMDS = []
NOTES = []
STUBBED = []
PER_CALL_SECONDS = 3
ALLOWED_SETUP = ("insert", "update", "delete", "create", "replace")
WRITE = re.compile(r"\s*(insert|update|delete|replace)\b", re.I)


class Timeout(BaseException):
    pass


class Unreached(Exception):
    """The statement the hypothesis is about was never executed: that is not evidence either way."""


# ---- stand-ins for modules that are not installed ---------------------------------------------------------

class Stub:
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return Stub()
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return Stub()
    def __getitem__(self, k): return Stub()
    def __iter__(self): return iter(())
    def __enter__(self): return self
    def __exit__(self, *a): return False


class StubModule(types.ModuleType):
    __path__ = []

    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return Stub()


class StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Last in sys.meta_path: only names nothing else could import end up here."""

    def find_spec(self, name, path, target=None):
        return importlib.machinery.ModuleSpec(name, self, is_package=True)

    def create_module(self, spec):
        STUBBED.append(spec.name)
        return StubModule(spec.name)

    def exec_module(self, module):
        return None


class _Env(dict):
    """os.environ['X'] for a variable nobody set must not abort the import of the module under test."""

    def __missing__(self, key):
        return "vishap-probe"

    def __setitem__(self, k, v):
        dict.__setitem__(self, k, str(v))


# ---- recorders for everything that leaves the process -----------------------------------------------------

class _Popen:
    returncode = 0

    def __init__(self, args=None, *a, **k):
        CMDS.append(_cmd_text(args))
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO("")
        self.stdin = io.StringIO("")

    def communicate(self, *a, **k): return ("", "")
    def wait(self, *a, **k): return 0
    def poll(self): return 0
    def kill(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _cmd_text(cmd):
    if isinstance(cmd, (list, tuple)):
        return " ".join(str(x) for x in cmd)
    return str(cmd)


def _system(cmd, *a, **k):
    CMDS.append(_cmd_text(cmd))
    return 0


def _popen_os(cmd, *a, **k):
    CMDS.append(_cmd_text(cmd))
    return io.StringIO("")


def _run(args, *a, **k):
    CMDS.append(_cmd_text(args))
    return subprocess.CompletedProcess(args, 0, "", "")


def _call(args, *a, **k):
    CMDS.append(_cmd_text(args))
    return 0


def _check_output(args, *a, **k):
    CMDS.append(_cmd_text(args))
    return ""


def _blocked(*a, **k):
    raise OSError("blocked by the probe (no network, no processes)")


def _open(file, mode="r", *a, **k):
    if isinstance(mode, str) and any(c in mode for c in "wax+"):
        return io.BytesIO() if "b" in mode else io.StringIO()
    return _real_open(file, mode, *a, **k)


def patch_stdlib():
    os.environ = _Env(os.environ)
    os.system = _system
    os.popen = _popen_os
    for n in ("execv", "execve", "execvp", "execl", "execlp", "spawnl", "spawnv", "fork", "forkpty", "kill"):
        if hasattr(os, n):
            setattr(os, n, _blocked)
    subprocess.run, subprocess.call, subprocess.check_call = _run, _call, _call
    subprocess.check_output, subprocess.Popen = _check_output, _Popen
    builtins.open = _open
    socket.socket.connect = _blocked
    socket.socket.connect_ex = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked


# ---- the database: one real in-memory connection behind a recording proxy ---------------------------------

class Hub:
    def __init__(self):
        self.real = None
        self.attrs = {}
        self.statements = []     # {"sql", "params"}
        self.rowcounts = []      # rowcount of every write
        self.interleave = None   # {"after", "sql", "done"}
        self.reset()

    def reset(self):
        if self.real is not None:
            with contextlib.suppress(Exception):
                self.real.close()
        self.real = _connect(":memory:", check_same_thread=False)
        for k, v in self.attrs.items():
            with contextlib.suppress(Exception):
                setattr(self.real, k, v)
        self.statements, self.rowcounts, self.interleave = [], [], None

    def raw(self):
        """A cursor that gives plain tuples whatever row_factory the module under test chose."""
        cur = self.real.cursor()
        return cur

    def fire(self):
        il = self.interleave
        if il and not il.get("done"):
            il["done"] = True
            cur = self.real.cursor()
            cur.execute(il["sql"])


HUB = Hub()


class PCur:
    def __init__(self, cur):
        object.__setattr__(self, "_c", cur)
        object.__setattr__(self, "_pending", False)

    def execute(self, sql, params=()):
        HUB.statements.append({"sql": str(sql), "params": params})
        self._c.execute(sql, params)
        text = str(sql)
        if WRITE.match(text):
            HUB.rowcounts.append(self._c.rowcount)
        il = HUB.interleave
        if il and not il.get("done") and text.lstrip().lower().startswith("select") \
                and il["after"].lower() in re.sub(r"\s+", " ", text).lower():
            object.__setattr__(self, "_pending", True)
        return self

    def executemany(self, sql, seq):
        HUB.statements.append({"sql": str(sql), "params": "<many>"})
        self._c.executemany(sql, seq)
        if WRITE.match(str(sql)):
            HUB.rowcounts.append(self._c.rowcount)
        return self

    def executescript(self, script):
        HUB.statements.append({"sql": str(script), "params": ()})
        self._c.executescript(script)
        return self

    def _after_fetch(self, value):
        if self._pending:
            object.__setattr__(self, "_pending", False)
            HUB.fire()
        return value

    def fetchone(self): return self._after_fetch(self._c.fetchone())
    def fetchall(self): return self._after_fetch(self._c.fetchall())
    def fetchmany(self, *a): return self._after_fetch(self._c.fetchmany(*a))

    def __iter__(self):
        return iter(self._after_fetch(self._c.fetchall()))

    def __getattr__(self, n): return getattr(self._c, n)
    def __setattr__(self, n, v): setattr(self._c, n, v)


class PConn:
    def cursor(self, *a, **k): return PCur(HUB.real.cursor())
    def execute(self, sql, params=()): return self.cursor().execute(sql, params)
    def executemany(self, sql, seq): return self.cursor().executemany(sql, seq)
    def executescript(self, script): return self.cursor().executescript(script)
    def commit(self): return HUB.real.commit()
    def rollback(self): return HUB.real.rollback()
    def close(self): return None
    def __enter__(self): return self

    def __exit__(self, et, ev, tb):
        (HUB.real.rollback if et else HUB.real.commit)()
        return False

    def __getattr__(self, n): return getattr(HUB.real, n)

    def __setattr__(self, n, v):
        HUB.attrs[n] = v
        setattr(HUB.real, n, v)


PROXY = PConn()


def fake_connect(*a, **k):
    return PROXY


def dump():
    cur = HUB.real.cursor()
    out = {}
    names = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    for t in names:
        out[t] = sorted((tuple(r) for r in HUB.real.cursor().execute(f'SELECT * FROM "{t}"').fetchall()), key=repr)
    return out


def diff_text(before, after, limit=3):
    parts = []
    for t in sorted(set(before) | set(after)):
        b, a = list(before.get(t, [])), list(after.get(t, []))
        gone = [r for r in b if r not in a]
        new = [r for r in a if r not in b]
        if not gone and not new:
            continue
        bits = [f"-{r!r}" for r in gone[:limit]] + [f"+{r!r}" for r in new[:limit]]
        extra = len(gone) + len(new) - len(bits)
        parts.append(f"{t}: " + " ".join(bits) + (f" (+{extra} more)" if extra > 0 else ""))
    return "; ".join(parts)


# ---- running one hypothesis -------------------------------------------------------------------------------

def dec(v):
    if isinstance(v, dict) and set(v) == {"$float"}:
        return float(v["$float"])
    if isinstance(v, list):
        return [dec(x) for x in v]
    if isinstance(v, dict):
        return {k: dec(x) for k, x in v.items()}
    return v


def _alarm(_s, _f):
    raise Timeout()


def _select_only(sql):
    s = str(sql).strip().rstrip(";")
    return s.lower().startswith("select") and ";" not in s


def _setup_ok(sql):
    s = str(sql).strip().rstrip(";")
    return s.lower().split(None, 1)[0:1] and s.lower().split(None, 1)[0] in ALLOWED_SETUP and ";" not in s


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return not (isinstance(a, float) and math.isnan(a)) and abs(float(a) - float(b)) < 1e-9
    return a == b


def _success(ret):
    if isinstance(ret, dict):
        if "error" in ret or str(ret.get("status", "")).lower() in ("error", "failed", "fail", "denied"):
            return False
        return bool(ret)
    return bool(ret)


def evaluate(chk, ctx):
    """-> (violated, text). Raises on a check that cannot be evaluated."""
    t = chk.get("type")
    if t == "db_unchanged":
        d = diff_text(ctx["before"], ctx["after"])
        return (bool(d), "stored data changed: " + d if d else "stored data is unchanged")
    if t in ("sql_equals", "sql_min"):
        if not _select_only(chk["sql"]):
            raise ValueError("check sql must be one SELECT")
        row = HUB.real.cursor().execute(chk["sql"]).fetchone()
        actual = row[0] if row else None
        label = chk.get("label") or chk["sql"]
        if t == "sql_equals":
            ok = _same(actual, chk["expect"])
            return (not ok, f"{label}: expected {chk['expect']!r}, got {actual!r}")
        ok = actual is not None and not (isinstance(actual, float) and math.isnan(actual)) and actual >= chk["min"]
        return (not ok, f"{label}: expected >= {chk['min']!r}, got {actual!r}")
    if t == "no_exception":
        e = ctx["exc"]
        return (e is not None, f"raised {type(e).__name__}: {e}" if e is not None else "no exception")
    if t == "rejects":
        e, ret = ctx["exc"], ctx["ret"]
        if e is not None or not _success(ret):
            return (False, f"refused ({type(e).__name__ if e is not None else repr(ret)})")
        return (True, f"returned {ret!r} instead of refusing")
    if t == "payload_in_sql":
        p = chk["payload"]
        if not HUB.statements:
            raise Unreached("no SQL statement was executed (the function returned or raised before reaching one)")
        for st in HUB.statements:
            if p in st["sql"]:
                return (True, "the probe text became part of the SQL statement: " + re.sub(r"\s+", " ", st["sql"]).strip()[:170])
        return (False, "the probe text only travelled as a bound parameter or not at all")
    if t == "payload_in_cmd":
        p = chk["payload"]
        if not CMDS:
            raise Unreached("no shell command was started (the function returned or raised before reaching one)")
        for c in CMDS:
            if p in c:
                return (True, "the probe text became part of the shell command: " + c[:170])
        return (False, "the probe text did not reach a shell command")
    if t == "no_success_without_effect":
        e, ret = ctx["exc"], ctx["ret"]
        if e is not None:
            raise Unreached(f"the function raised {type(e).__name__} before it could report anything")
        if not HUB.rowcounts:
            raise Unreached("the function executed no write")
        if _success(ret) and all(rc == 0 for rc in HUB.rowcounts):
            return (True, f"returned {ret!r} but every write affected 0 rows")
        return (False, "no false success")
    raise ValueError(f"unknown check type {t!r}")


def call_text(name, args, kwargs):
    bits = [repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()]
    s = f"{name}({', '.join(bits)})"
    return s if len(s) < 140 else s[:137] + "..."


def run_one(h, mod, spans, schema):
    res = {"id": h.get("id"), "function": h.get("function"), "kind": h.get("kind"), "title": h.get("title", ""),
           "invariant": h.get("invariant", ""), "start": spans.get(h.get("function"), (0, 0))[0],
           "end": spans.get(h.get("function"), (0, 0))[1], "check": "", "status": "INCONCLUSIVE", "evidence": ""}
    fn = getattr(mod, str(h.get("function")), None)
    if not callable(fn):
        res["evidence"] = f"function {h.get('function')!r} not found in the module"
        return res
    args, kwargs = dec(h.get("args") or []), dec(h.get("kwargs") or {})
    try:
        inspect.signature(fn).bind(*args, **kwargs)
    except TypeError as e:
        res["evidence"] = f"arguments do not fit the signature: {e}"
        return res
    HUB.reset()
    try:
        cur = HUB.real.cursor()
        for s in schema:
            cur.execute(s)
        for s in h.get("setup") or []:
            if not _setup_ok(s):
                raise ValueError("setup statement not allowed: " + str(s)[:60])
            cur.execute(s)
        HUB.real.commit()
    except Exception as e:
        res["evidence"] = f"fixture could not be built: {type(e).__name__}: {e}"
        return res
    il = h.get("interleave")
    if il:
        if not _setup_ok(il.get("sql", "")):
            res["evidence"] = "interleave statement not allowed"
            return res
        HUB.interleave = {"after": str(il["after"]), "sql": il["sql"], "done": False}
    CMDS.clear()
    before = dump()
    ret, exc = None, None
    old = signal.signal(signal.SIGALRM, _alarm) if hasattr(signal, "SIGALRM") else None
    try:
        if old is not None:
            signal.setitimer(signal.ITIMER_REAL, PER_CALL_SECONDS)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            ret = fn(*args, **kwargs)
    except Timeout:
        res["evidence"] = f"{call_text(h['function'], args, kwargs)} did not finish in {PER_CALL_SECONDS}s"
        return res
    except BaseException as e:   # noqa: BLE001 - the function under test may raise anything
        exc = e
    finally:
        if old is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
    try:
        after = dump()
        ctx = {"before": before, "after": after, "ret": ret, "exc": exc}
        outcomes = []
        for chk in h.get("checks") or []:
            outcomes.append((chk, *evaluate(chk, ctx)))
    except Unreached as e:
        res["evidence"] = f"{call_text(h['function'], args, kwargs)}: {e}"
        return res
    except Exception as e:
        res["evidence"] = f"check could not be evaluated: {type(e).__name__}: {e}"
        return res
    if not outcomes:
        res["evidence"] = "no checks"
        return res
    what = call_text(h["function"], args, kwargs)
    note = " [another writer's update was injected between the read and the write]" if il else ""
    bad = next(((c, t) for c, v, t in outcomes if v), None)
    if bad:
        res["status"], res["check"] = "CONFIRMED", bad[0].get("type", "")
        res["evidence"] = f"{what}{note}: {bad[1]}"
    else:
        res["status"], res["check"] = "NOT_REPRODUCED", outcomes[0][0].get("type", "")
        res["evidence"] = f"{what}{note}: invariant held ({outcomes[0][2]})"
    res["exception"] = None if exc is None else f"{type(exc).__name__}: {exc}"[:200]
    return res


def spans_of(source):
    out = {}
    try:
        for n in ast.parse(source).body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[n.name] = (n.lineno, getattr(n, "end_lineno", n.lineno))
    except SyntaxError:
        pass
    return out


def main():
    out = {"framework": "functions", "handlers": 0, "results": [], "notes": NOTES, "error": None}
    real_stdout = sys.stdout
    try:
        target, spec_path = sys.argv[1], sys.argv[2]
        source = _real_open(target, encoding="utf-8").read()
        spec = json.loads(_real_open(spec_path, encoding="utf-8").read())
        patch_stdlib()
        sqlite3.connect = fake_connect
        sys.meta_path.append(StubFinder())
        mod = types.ModuleType("target")
        mod.__file__ = target
        sys.modules["target"] = mod
        old = signal.signal(signal.SIGALRM, _alarm) if hasattr(signal, "SIGALRM") else None
        try:
            if old is not None:
                signal.setitimer(signal.ITIMER_REAL, 5)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exec(compile(source, target, "exec"), mod.__dict__)
        except Timeout:
            out["error"] = "the module did not finish loading in 5s"
        except BaseException as e:   # noqa: BLE001
            out["error"] = f"the module could not be loaded: {type(e).__name__}: {e}"[:300]
        finally:
            if old is not None:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old)
        if STUBBED:
            NOTES.append("modules that are not installed were replaced by stubs: " + ", ".join(sorted(set(STUBBED))[:8]))
        if not out["error"]:
            spans = spans_of(source)
            for h in (spec.get("hypotheses") or [])[:80]:
                try:
                    out["results"].append(run_one(h, mod, spans, spec.get("schema") or []))
                except BaseException as e:   # noqa: BLE001 - one bad hypothesis must not lose the rest
                    out["results"].append({"id": h.get("id"), "function": h.get("function"), "kind": h.get("kind"),
                                           "status": "INCONCLUSIVE", "check": "", "start": 0, "end": 0,
                                           "evidence": f"{type(e).__name__}: {e}"[:200]})
            out["handlers"] = len({r["function"] for r in out["results"]})
    except BaseException as e:   # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"[:300]
    real_stdout.write("\n" + json.dumps(out, default=str) + "\n")
    real_stdout.flush()


if __name__ == "__main__":
    main()
