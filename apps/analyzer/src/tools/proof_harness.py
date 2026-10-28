# -*- coding: utf-8 -*-
"""Runs INSIDE the proof subprocess (see proof.py). stdlib only, no imports from src.

It loads the submitted module with a fake ``flask`` and a recording ``sqlite3``, then calls
every HTTP handler with probe values and records what the handler tried to do: which SQL text
it executed, which file paths it opened or served, which shell commands it started.

Nothing real happens: ``open`` returns an in-memory buffer, file/shell/network functions are
replaced by recorders, ``sqlite3.connect`` returns a recorder. This is a best-effort stub layer;
the real containment is the bubblewrap/namespace wrapper that proof.py puts around this process.

Usage:  python -I proof_harness.py <target.py>   ->  last stdout line is a JSON document.
"""
import builtins
import dis
import importlib.abc
import importlib.machinery
import inspect
import io
import json
import os
import re
import sys
import types

MARK = "VSHPQ"
SQLI = "VSHPQ' OR '1'='1"
TRAV = "../../VSHPQ_etc/passwd"
ABS = "/VSHPQ_abs/passwd"
NEG = -7340017
BIG = 10 ** 9
NUMERIC = {"page", "size", "limit", "offset", "id", "amount", "qty", "quantity", "count", "per_page",
           "page_size", "price", "total", "sum", "from", "to", "user_id", "account_id", "item_id"}
AMOUNT = {"amount", "price", "qty", "quantity", "count", "total", "sum"}
WRITE = ("insert", "update", "delete", "replace", "drop", "alter")

REC = {"sql": [], "files": [], "blocked": [], "exec": [], "net": []}
HANDLERS = []      # (path, methods, func)
BEFORE = []        # before_request hooks
_real_open = builtins.open
_state = {"mode": "auth"}


class Abort(Exception):
    def __init__(self, code=500, *a):
        super().__init__(code)
        self.code = code


class Dummy:
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return Dummy()
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return Dummy()
    def __getitem__(self, k): return Dummy()
    def __iter__(self): return iter(())
    def __bool__(self): return True
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __int__(self): return 1
    def __str__(self): return ""


class UModule(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return Dummy()


class _Missing(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Last resort: a module that is not installed becomes a harmless stand-in."""
    def find_spec(self, name, path, target=None):
        return importlib.machinery.ModuleSpec(name, self, is_package=True)
    def create_module(self, spec):
        m = UModule(spec.name)
        m.__path__ = []
        return m
    def exec_module(self, module):
        pass


# ----------------------------------------------------------------------------- request
def _probe(key, mode, typed):
    k = str(key).lower()
    numeric = k in NUMERIC
    if mode == "amount" and k in AMOUNT:
        return NEG if typed else str(NEG)
    if numeric:
        return 1 if typed else "1"
    if mode == "sqli" or mode == "cmdi":
        return SQLI
    if mode == "traversal":
        return TRAV
    if mode == "traversal_abs":
        return ABS
    return "abc"


class Params(dict):
    def __init__(self, typed):
        super().__init__()
        self.typed = typed
    def get(self, key, default=None, type=None):
        v = _probe(key, _state["mode"], self.typed)
        if type is not None:
            try:
                return type(v)
            except Exception:
                return default
        return v
    def __getitem__(self, key): return _probe(key, _state["mode"], self.typed)
    def __contains__(self, key): return True
    def getlist(self, key): return [self.get(key)]
    def to_dict(self, *a, **k): return {}


class Headers(dict):
    def get(self, key, default=None): return default


class Request:
    def __init__(self):
        self.args = Params(False)
        self.form = Params(False)
        self.values = Params(False)
        self._json = Params(True)
        self.headers = Headers()
        self.cookies = {}
        self.files = {}
        self.data = b""
        self.method = "POST"
        self.remote_addr = "127.0.0.1"
        self.authorization = None
        self.path = "/"
        self.url = "http://localhost/"
        self.host = "localhost"
        self.is_json = True
    @property
    def json(self): return self._json
    def get_json(self, *a, **k): return self._json


REQUEST = Request()


# ----------------------------------------------------------------------------- flask
def _deco(app, path, methods):
    def wrap(fn):
        HANDLERS.append((path, [m.upper() for m in methods], fn))
        return fn
    return wrap


class Flask:
    def __init__(self, *a, **k):
        self.config = {}
    def route(self, path, methods=None, **k): return _deco(self, path, methods or ["GET"])
    def get(self, path, **k): return _deco(self, path, ["GET"])
    def post(self, path, **k): return _deco(self, path, ["POST"])
    def put(self, path, **k): return _deco(self, path, ["PUT"])
    def delete(self, path, **k): return _deco(self, path, ["DELETE"])
    def patch(self, path, **k): return _deco(self, path, ["PATCH"])
    def before_request(self, fn):
        BEFORE.append(fn)
        return fn
    before_app_request = before_request
    def run(self, *a, **k): return None
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))


def _abort(code=500, *a, **k):
    raise Abort(code)


def _jsonify(*a, **k):
    return k if k else (a[0] if len(a) == 1 else list(a))


def _send_file(path, *a, **k):
    REC["files"].append(("send_file", str(path)))
    return "FILE"


def _send_from_directory(directory, path, **k):
    base = os.path.normpath(str(directory))
    full = os.path.normpath(os.path.join(base, str(path)))
    if os.path.isabs(str(path)) or not (full == base or full.startswith(base + os.sep)):
        REC["blocked"].append(("send_from_directory", str(path)))
        raise Abort(404)
    REC["files"].append(("send_from_directory", full))
    return "FILE"


def _redirect(url, *a, **k):
    REC["files"].append(("redirect", str(url)))
    return "REDIRECT"


class _Session(dict):
    """flask.session. The 'auth' probe runs with an empty session (a stranger). Every other probe runs as a
    logged-in user (any key reads as set), so an injection hidden behind @login_required is still tested
    instead of being masked by the 401."""
    def _in(self):
        return _state["mode"] != "auth"

    def get(self, key, default=None):
        return "probe-user" if self._in() else dict.get(self, key, default)

    def __getitem__(self, key):
        return "probe-user" if self._in() else dict.__getitem__(self, key)

    def __contains__(self, key):
        return True if self._in() else dict.__contains__(self, key)


def make_flask():
    m = types.ModuleType("flask")
    m.Flask = Flask
    m.Blueprint = lambda *a, **k: Flask()
    m.request = REQUEST
    m.jsonify = _jsonify
    m.abort = _abort
    m.send_file = _send_file
    m.send_from_directory = _send_from_directory
    m.redirect = _redirect
    m.session = _Session()
    m.g = types.SimpleNamespace()
    m.current_app = Dummy()
    m.render_template_string = lambda *a, **k: ""
    m.render_template = lambda *a, **k: ""
    m.make_response = lambda *a, **k: Dummy()
    m.Response = Dummy
    m.url_for = lambda *a, **k: "/"
    m.__getattr__ = lambda n: Dummy()
    return m


# ----------------------------------------------------------------------------- sqlite3
class UniRow(tuple):
    def __getitem__(self, i): return BIG
    def __iter__(self): return iter((BIG, BIG))
    def __len__(self): return 2


class RecCursor:
    rowcount = 1
    lastrowid = 1
    description = None
    def execute(self, sql, params=()):
        REC["sql"].append((str(sql), repr(params)))
        return self
    executemany = execute
    def executescript(self, sql):
        REC["sql"].append((str(sql), "()"))
        return self
    def fetchone(self): return UniRow((BIG,))
    def fetchall(self): return []
    def fetchmany(self, n=1): return []
    def __iter__(self): return iter(())
    def close(self): return None


class RecConn(RecCursor):
    row_factory = None
    total_changes = 1
    def cursor(self): return RecCursor()
    def commit(self): return None
    def rollback(self): return None
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Env(dict):
    """os.environ stand-in: a required variable that is not set (os.environ["APP_SECRET_KEY"]) yields a
    placeholder instead of killing the import, which would hide every handler in the file."""
    def __missing__(self, key):
        return "proof-placeholder"


def patch_stdlib():
    import sqlite3
    sqlite3.connect = lambda *a, **k: RecConn()
    os.environ = _Env((k, v) for k, v in os.environ.items() if k in ("PATH", "LANG", "HOME", "TMPDIR"))

    def fake_open(file, mode="r", *a, **k):
        if isinstance(file, int):
            return _real_open(file, mode, *a, **k)
        REC["files"].append(("open", str(file)))
        return io.BytesIO(b"") if "b" in mode else io.StringIO("")
    builtins.open = fake_open
    io.open = fake_open

    def rec_exec(name):
        def f(*a, **k):
            cmd = a[0] if a else k.get("args", "")
            REC["exec"].append((name, cmd if isinstance(cmd, str) else list(map(str, cmd)) if isinstance(cmd, (list, tuple)) else str(cmd), bool(k.get("shell"))))
            return Dummy()
        return f
    import subprocess
    for n in ("Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"):
        if hasattr(subprocess, n):
            setattr(subprocess, n, rec_exec("subprocess." + n))
    for n in ("system", "popen", "execv", "execve", "execvp", "execl", "execlp", "spawnl", "spawnv", "fork", "kill"):
        if hasattr(os, n):
            setattr(os, n, rec_exec("os." + n))
    for n in ("remove", "unlink", "rmdir", "removedirs", "rename", "replace", "mkdir", "makedirs", "chmod", "chown", "symlink", "link", "truncate"):
        if hasattr(os, n):
            setattr(os, n, (lambda nm: (lambda *a, **k: REC["files"].append(("os." + nm, str(a[0]) if a else ""))))(n))
    import shutil
    for n in ("rmtree", "move", "copy", "copy2", "copyfile", "copytree"):
        setattr(shutil, n, (lambda nm: (lambda *a, **k: REC["files"].append(("shutil." + nm, str(a[0]) if a else ""))))(n))
    import socket

    class _NoSock:
        def __init__(self, *a, **k):
            REC["net"].append("socket")
            raise OSError("network blocked by proof harness")
    socket.socket = _NoSock
    socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(OSError("network blocked by proof harness"))
    socket.getaddrinfo = lambda *a, **k: (_ for _ in ()).throw(OSError("network blocked by proof harness"))



# ------------------------------------------------------------- stdlib http.server
def _stdlib_paths(source, method):
    """Paths a do_* method compares self.path against, read from the source."""
    import ast as _ast
    found = []
    try:
        tree = _ast.parse(source)
    except SyntaxError:
        return ["/"]
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.FunctionDef) or node.name != method:
            continue
        for cmp in _ast.walk(node):
            if isinstance(cmp, _ast.Compare) and cmp.comparators:
                value = getattr(cmp.comparators[0], "value", None)
                if isinstance(value, str) and value.startswith("/"):
                    found.append(value)
            if isinstance(cmp, _ast.Call) and getattr(cmp.func, "attr", "") == "startswith":
                if cmp.args and isinstance(getattr(cmp.args[0], "value", None), str):
                    found.append(cmp.args[0].value)
    return sorted(set(found)) or ["/"]


def _stdlib_call(cls, method, path, body):
    """A zero-argument callable that runs one do_* method against a fake request."""
    def call():
        obj = cls.__new__(cls)
        status = {"code": 200}
        obj.path = path
        obj.command = method.replace("do_", "")
        obj.requestline = obj.command + " " + path + " HTTP/1.1"
        obj.request_version = "HTTP/1.1"
        obj.headers = {"Content-Length": str(len(body)), "Content-Type": "application/json",
                       "Host": "127.0.0.1"}
        obj.rfile = io.BytesIO(body)
        obj.wfile = io.BytesIO()
        obj.client_address = ("127.0.0.1", 40000)
        obj.server = types.SimpleNamespace(server_name="127.0.0.1", server_port=8000)
        obj.log_message = lambda *a, **k: None
        obj.log_error = lambda *a, **k: None
        obj.send_response = lambda code, message=None: status.update(code=int(code))
        obj.send_header = lambda *a, **k: None
        obj.endheaders = lambda: None
        obj.send_error = lambda code, message=None, explain=None: status.update(code=int(code))
        obj.close_connection = False
        getattr(obj, method)()
        return status["code"]
    return call


def _register_stdlib(ns, source):
    """Register http.server handlers so prove works on stdlib services too.

    A do_* method is a handler in the same sense a Flask route is: a path, a method
    and a body that comes from outside. The fake request keeps the same shape the
    real one has — path, headers, rfile — so the recorded calls look identical.
    """
    for _name, obj in list(ns.items()):
        if not isinstance(obj, type):
            continue
        methods = [m for m in ("do_GET", "do_POST", "do_PUT", "do_DELETE", "do_PATCH")
                   if hasattr(obj, m)]
        if not methods:
            continue
        for method in methods:
            http_method = method.replace("do_", "")
            if http_method == "GET":
                body = b""
            else:
                body = json.dumps({"material": MARK, "message": MARK, "question": MARK,
                                   "text": MARK, "path": MARK}).encode("utf-8")
            for path in _stdlib_paths(source, method):
                HANDLERS.append((path, [http_method], _stdlib_call(obj, method, path, body)))

# ----------------------------------------------------------------------------- runner
def _call(fn, mode):
    sig = inspect.signature(fn)
    kwargs = {}
    for name, p in sig.parameters.items():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        if p.default is not inspect._empty:
            continue
        kwargs[name] = _probe(name, mode, True)
    for hook in BEFORE:
        hook()
    return fn(**kwargs)


def _span(fn):
    code = getattr(fn, "__code__", None)
    if code is None:
        return 0, 0
    lines = [ln for _, ln in dis.findlinestarts(code) if ln]
    return code.co_firstlineno, (max(lines) if lines else code.co_firstlineno)


def _eval(mode, outcome):
    sql, files, execs = REC["sql"], REC["files"], REC["exec"]
    aborted = outcome.get("abort")
    if mode == "sqli":
        for s, p in sql:
            if MARK in s:
                return "CONFIRMED", "payload is part of the executed SQL text: " + s[:200]
        if sql:
            return "NOT_REPRODUCED", "payload reached the database only as a bound parameter"
        return "INCONCLUSIVE", "handler made no sqlite3 call (other database library or failed before it)"
    if mode == "cmdi":
        for name, cmd, shell in execs:
            if isinstance(cmd, str) and MARK in cmd:
                return "CONFIRMED", f"payload is part of the command string passed to {name}: {cmd[:200]}"
        if execs:
            return "NOT_REPRODUCED", "command is an argument list, payload is not interpreted by a shell"
        return "INCONCLUSIVE", "handler started no process"
    if mode in ("traversal", "traversal_abs"):
        want = "../../VSHPQ_etc" if mode == "traversal" else "/VSHPQ_abs"
        for kind, path in files:
            if kind in ("send_file", "open", "send_from_directory") and (want in path if mode == "traversal" else path.startswith(want)):
                what = "'../' reaches the file API unchanged" if mode == "traversal" else "an absolute path replaces the base directory"
                return "CONFIRMED", f"{what}: {kind}({path[:160]})"
        if REC["blocked"]:
            return "NOT_REPRODUCED", "path was rejected by a safe join (send_from_directory)"
        if files:
            return "NOT_REPRODUCED", "file API was called, but not with the probe path"
        return "INCONCLUSIVE", "handler touched no file API"
    if mode == "amount":
        for s, p in sql:
            if s.strip().split(" ", 1)[0].lower() in WRITE and str(NEG) in p:
                return "CONFIRMED", f"negative amount reaches the write: {s[:120]} params={p[:80]}"
        if aborted and 400 <= aborted < 500:
            return "NOT_REPRODUCED", f"handler rejected the request with HTTP {aborted}"
        if any(s.strip().split(" ", 1)[0].lower() in WRITE for s, _ in sql):
            return "NOT_REPRODUCED", "a write ran, but the negative amount did not reach it"
        return "INCONCLUSIVE", "handler did not reach a write (failed or returned earlier)"
    if mode == "auth":
        acted = bool(sql or files or execs)
        if aborted in (401, 403):
            return "NOT_REPRODUCED", f"handler answered HTTP {aborted} without credentials"
        sensitive = bool(files or execs) or any(
            s.strip().split(" ", 1)[0].lower() in WRITE or re.search(r"\busers?\b|\baccounts?\b|e-?mail|passw|secret", s, re.I)
            for s, _ in sql)
        if acted and not sensitive:
            return "INCONCLUSIVE", "handler acted without credentials, but only on non-sensitive reads"
        if acted and not outcome.get("error_before_action"):
            first = sql[0][0][:100] if sql else (str(files[0]) if files else str(execs[0]))
            return "CONFIRMED", f"handler acted without any credentials ({len(sql)} db call(s), {len(files)} file op(s)); first: {first}"
        return "INCONCLUSIVE", "handler failed before doing anything: " + str(outcome.get("error", ""))[:100]
    return "INCONCLUSIVE", "unknown check"


MODES = ("auth", "sqli", "cmdi", "traversal", "traversal_abs", "amount")
PUBLIC = re.compile(r"^/?(login|logout|signin|signup|register|health|healthz|ping|status|docs|redoc|openapi\.json|metrics|favicon\.ico|static.*)?/?$", re.I)



def _stub_relative_package(source):
    """Give relative imports something to land on.

    A file that does `from .chat import reply` cannot be exec'd on its own; the harness
    used to give up with an ImportError and report «no handlers». Stubbing the package
    keeps the target's own code intact while the neighbours become no-ops — enough to
    reach the handler bodies, which is all a probe needs.
    """
    import ast as _ast
    names = set()
    try:
        tree = _ast.parse(source)
    except SyntaxError:
        return None
    for node in _ast.walk(tree):
        if isinstance(node, _ast.ImportFrom) and node.level and node.module:
            names.add(node.module)
    if not names:
        return None
    pkg = "proof_target_pkg"
    root = types.ModuleType(pkg)
    root.__path__ = []
    sys.modules[pkg] = root
    for name in sorted(names):
        full = pkg
        for part in name.split("."):
            full += "." + part
            module = types.ModuleType(full)
            module.__path__ = []
            module.__getattr__ = lambda attr: (lambda *a, **k: None)
            sys.modules.setdefault(full, module)
    return pkg

def main():
    path = sys.argv[1]
    with _real_open(path, "rb") as f:
        source = f.read().decode("utf-8", "replace")
    out = {"framework": "flask", "handlers": 0, "results": [], "notes": [], "error": None}
    if re.search(r"^\s*(from|import)\s+fastapi\b", source, re.M):
        out["error"] = "framework not supported: fastapi"
        print(json.dumps(out)); return
    sys.modules["flask"] = make_flask()
    sys.meta_path.append(_Missing())
    patch_stdlib()
    try:
        import signal
        def _timeout(*a): raise TimeoutError("handler timeout")
        signal.signal(signal.SIGALRM, _timeout)
        have_alarm = True
    except Exception:
        have_alarm = False
    ns = {"__name__": "proof_target", "__file__": path}
    try:
        if have_alarm: signal.alarm(4)
        exec(compile(source, path, "exec"), ns)
        if have_alarm: signal.alarm(0)
    except BaseException as e:
        out["notes"].append(f"module import raised {type(e).__name__}: {str(e)[:120]}")
        if isinstance(e, ImportError) and "relative import" in str(e):
            pkg = _stub_relative_package(source)
            if pkg:
                ns = {"__name__": pkg + ".target", "__package__": pkg, "__file__": path}
                try:
                    if have_alarm: signal.alarm(4)
                    exec(compile(source, path, "exec"), ns)
                    if have_alarm: signal.alarm(0)
                    out["notes"].append("relative imports were stubbed to reach the handlers")
                except BaseException as again:
                    out["notes"].append(f"second import raised {type(again).__name__}: {str(again)[:120]}")
    if not HANDLERS:
        _register_stdlib(ns, source)
        if HANDLERS:
            out["framework"] = "http.server"
    out["handlers"] = len(HANDLERS)
    if not HANDLERS:
        out["error"] = "no Flask-style or http.server handlers found"
    for route, methods, fn in HANDLERS:
        start, end = _span(fn)
        for mode in MODES:
            for k in REC: REC[k].clear()
            _state["mode"] = mode
            outcome = {}
            try:
                if have_alarm: signal.alarm(3)
                _call(fn, mode)
            except Abort as a:
                outcome["abort"] = a.code
            except BaseException as e:
                outcome["error"] = f"{type(e).__name__}: {e}"
                outcome["error_before_action"] = not (REC["sql"] or REC["files"] or REC["exec"])
            finally:
                if have_alarm: signal.alarm(0)
            if mode == "auth" and re.match(PUBLIC, route):
                status, evidence = "INCONCLUSIVE", "public route by design"
            else:
                status, evidence = _eval(mode, outcome)
            out["results"].append({"route": route, "methods": methods, "function": getattr(fn, "__name__", "?"),
                                   "start": start, "end": end, "check": mode, "status": status,
                                   "evidence": evidence})
    print(json.dumps(out))


if __name__ == "__main__":
    main()
