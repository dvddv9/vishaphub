"""REST API and web form, standard library only.

    GET  /              the web form
    GET  /health        {"ok": true}
    GET  /api/status    version, what is installed, whether a model is configured
    GET  /api/examples  the example specs of the form
    POST /api/check     {"spec": "<yaml text>"}                -> Intake and Design only
    POST /api/generate  {"spec": "<yaml text>", "gate": false, "repairs": 2,
                         "no_analyzer": false}                 -> all five stages

The API never writes to the server's disk: Deliver runs as a dry run and
the files come back in the answer. Writing to a folder is the command
line's job.

Safety:
- Binds to 127.0.0.1 by default. A non-loopback host needs
  GENERATOR_API_TOKEN, sent as `Authorization: Bearer <token>`.
- Only application/json bodies (a web page on another site cannot send
  those without a preflight, which this server does not answer), and the
  Host and Origin headers must match this server.
- One generate run at a time (a run costs model tokens); the next gets 429.
- Request body up to 256 KB.
- The browser may send its own model settings (`llm`: url, model, key, thinking) for one request.
  They are never stored or logged. Accepted only when bound to loopback, or with
  GENERATOR_ALLOW_CLIENT_LLM=1 (otherwise the server would call any URL a client names).
"""

from __future__ import annotations

import hmac
import importlib.util
import json
import os
import shlex
import shutil
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from generator import __version__
from generator.tools.examples import examples
from generator.llm import LLMConfigError, config_from_env
from generator.pipeline.orchestrator import DEFAULT_REPAIRS, run_pipeline

MAX_BODY = 256 * 1024
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
WEB = Path(__file__).with_name("web") / "index.html"
_RUN_LOCK = threading.Lock()


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


LLM_FIELDS = {"url": "CUSTOM_LLM_URL", "model": "CUSTOM_LLM_MODEL", "key": "CUSTOM_LLM_KEY",
              "thinking": "CUSTOM_LLM_THINKING"}


def client_llm_config(llm):
    """The model settings a request brings along, checked like the environment ones.

    They live for this one request only: nothing is stored, logged or returned.
    """
    if llm is None:
        return None
    if not isinstance(llm, dict):
        raise ApiError(400, '"llm" must be an object')
    env = {}
    for field, name in LLM_FIELDS.items():
        v = llm.get(field, "")
        if not isinstance(v, str):
            raise ApiError(400, f'"llm.{field}" must be text')
        env[name] = v
    try:
        return config_from_env(env)
    except LLMConfigError as e:
        raise ApiError(400, f"llm: {e}") from None


def status(token: str | None, client_llm: bool) -> dict:
    try:
        config_from_env()
        llm_env = True
    except LLMConfigError:
        llm_env = False
    analyzer_cmd = shlex.split(os.environ.get("VISHAP_ANALYZER_CMD") or "vishap")
    return {
        "version": __version__,
        "llm_from_environment": llm_env,
        "client_llm_allowed": client_llm,
        "token_required": bool(token),
        "analyzer_found": bool(analyzer_cmd) and shutil.which(analyzer_cmd[0]) is not None,
        "coverage": "package" if importlib.util.find_spec("coverage") else "built-in",
        "ruff_found": shutil.which("ruff") is not None,
    }


def handle_generate(body: dict, *, check_only: bool, run=run_pipeline, client_llm: bool = True,
                    **run_kwargs) -> dict:
    spec_text = body.get("spec")
    if not isinstance(spec_text, str) or not spec_text.strip():
        raise ApiError(400, '"spec" must be the text of a spec.yaml')
    if len(spec_text) > 100_000:
        raise ApiError(413, "spec is too long")
    repairs = body.get("repairs", DEFAULT_REPAIRS)
    if not isinstance(repairs, int) or isinstance(repairs, bool) or not 0 <= repairs <= 5:
        raise ApiError(400, '"repairs" must be an integer from 0 to 5')
    gate = bool(body.get("gate", False))
    config = None
    if body.get("llm") is not None:
        if not client_llm:
            raise ApiError(403, "this server does not take model settings from the browser")
        config = client_llm_config(body["llm"])
    if not check_only and not _RUN_LOCK.acquire(blocking=False):
        raise ApiError(429, "another run is in progress")
    try:
        with tempfile.TemporaryDirectory(prefix="vg-api-") as tmp:
            path = Path(tmp) / "spec.yaml"
            path.write_text(spec_text, encoding="utf-8")
            log: list[str] = []
            kwargs = dict(gate=gate, no_llm=check_only, repairs=repairs, allow_write=False,
                          require_coverage=bool(body.get("require_coverage", False)),
                          text_check=bool(body.get("text_check", True)), log=log.append)
            if config is not None:
                kwargs["config"] = config
            if body.get("no_analyzer"):
                kwargs["analyzer"] = None
            kwargs.update(run_kwargs)
            res = run(path, **kwargs)
    finally:
        if not check_only:
            _RUN_LOCK.release()
    out = res.to_dict()
    out["log"] = log
    if res.files and res.design:
        planned = {f.path for f in res.design.files}
        out["files"] = {p: c for p, c in res.files.items() if p in planned}
    if res.deliver:
        out["trace"] = res.deliver.trace
        out["diff"] = res.deliver.diff      # against an empty folder: the API never reads the disk
    return out


def _status_for(out: dict) -> int:
    err = out.get("error") or ""
    if not err:
        return 200
    if err.startswith("spec:"):
        return 422          # the spec itself is wrong
    if err.startswith("build:"):
        return 502          # the model failed or answered unusably
    return 500


def make_handler(token: str | None, host_names: set[str], run=run_pipeline, run_kwargs=None,
                 client_llm: bool = True):
    run_kwargs = run_kwargs or {}

    class Handler(BaseHTTPRequestHandler):
        server_version = "vishap-generator"

        def log_message(self, fmt, *args):      # no request log with spec text in it
            pass

        def _send(self, status: int, payload, content_type="application/json"):
            data = payload if isinstance(payload, bytes) else json.dumps(
                payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; style-src 'unsafe-inline'; "
                             "script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            if host not in host_names:
                return False
            origin = self.headers.get("Origin")
            if origin:
                o = urlsplit(origin)
                if (o.hostname or "").lower() not in host_names:
                    return False
            return True

        def _auth_ok(self) -> bool:
            if not token:
                return True
            got = self.headers.get("Authorization", "")
            return got.startswith("Bearer ") and hmac.compare_digest(got[7:], token)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "bad Host or Origin"})
            path = urlsplit(self.path).path
            if path == "/health":
                return self._send(200, {"ok": True})
            if path == "/api/status":
                return self._send(200, status(token, client_llm))
            if path == "/api/examples":
                return self._send(200, {"examples": examples()})
            if path == "/":
                try:
                    return self._send(200, WEB.read_bytes(), "text/html")
                except OSError:
                    return self._send(500, {"error": "web form is missing"})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok():
                return self._send(403, {"error": "bad Host or Origin"})
            if not self._auth_ok():
                return self._send(401, {"error": "missing or wrong token"})
            path = urlsplit(self.path).path
            if path not in ("/api/generate", "/api/check"):
                return self._send(404, {"error": "not found"})
            if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
                return self._send(415, {"error": "Content-Type must be application/json"})
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._send(411, {"error": "Content-Length is required"})
            if length < 0 or length > MAX_BODY:
                return self._send(413, {"error": "body is too large"})
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(body, dict):
                    raise ValueError("not an object")
            except (ValueError, UnicodeDecodeError):
                return self._send(400, {"error": "body must be a JSON object"})
            try:
                out = handle_generate(body, check_only=path == "/api/check", run=run,
                                      client_llm=client_llm, **run_kwargs)
            except ApiError as e:
                return self._send(e.status, {"error": e.message})
            self._send(_status_for(out), out)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8787) -> int:
    token = os.environ.get("GENERATOR_API_TOKEN") or None
    if host not in LOOPBACK and not token:
        print("error: a non-loopback host needs GENERATOR_API_TOKEN", flush=True)
        return 2
    names = set(LOOPBACK) | {host.lower()}
    # Model settings from the browser mean the server calls a URL the browser names:
    # fine on this computer, not on a shared server unless the operator says so.
    client_llm = host in LOOPBACK or os.environ.get("GENERATOR_ALLOW_CLIENT_LLM") == "1"
    httpd = ThreadingHTTPServer((host, port), make_handler(token, names, client_llm=client_llm))
    print(f"vishap-generator on http://{host}:{port}/  (Ctrl+C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
