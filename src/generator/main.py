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

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from generator.api.auth import host_ok, token_ok
from generator.api.errors import ApiError
from generator.api.jobs import handle_generate
from generator.api.llm_config import status
from generator.api.reports import http_status
from generator.config import (DEFAULT_HOST, DEFAULT_PORT, LOOPBACK, MAX_BODY, WEB_INDEX,
                              allow_client_llm, api_token)
from generator.pipeline.orchestrator import run_pipeline
from generator.tools.examples import examples


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
            return host_ok(self.headers.get("Host"), self.headers.get("Origin"), host_names)

        def _auth_ok(self) -> bool:
            return token_ok(self.headers.get("Authorization"), token)

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
                    return self._send(200, WEB_INDEX.read_bytes(), "text/html")
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
            self._send(http_status(out), out)

    return Handler


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    token = api_token()
    if host not in LOOPBACK and not token:
        print("error: a non-loopback host needs GENERATOR_API_TOKEN", flush=True)
        return 2
    names = set(LOOPBACK) | {host.lower()}
    # Model settings from the browser mean the server calls a URL the browser names:
    # fine on this computer, not on a shared server unless the operator says so.
    client_llm = allow_client_llm(host)
    httpd = ThreadingHTTPServer((host, port), make_handler(token, names, client_llm=client_llm))
    print(f"vishap-generator on http://{host}:{port}/  (Ctrl+C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
