"""HTTP face for the hub: `GET /health`, `POST /run`, `GET /`.

The hub is a library first; this module is the smallest possible wrapper so the same
code can answer over the wire. Standard library only — the service must start in a
second, and a web framework is not what makes routing correct.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .pipeline import run_plan
from .router import RouteError, plan_for
from .services import ServiceConfig
from .version import __version__

MAX_BODY = 2_000_000

INDEX = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>VishapHub</title>
<style>
 body{background:#0b0f0e;color:#d7e0dc;font:16px/1.6 ui-monospace,Menlo,monospace;margin:0;padding:48px}
 h1{font-weight:500;letter-spacing:.02em;margin:0 0 8px}
 p{color:#8fa39c;max-width:60ch}
 code{color:#7fd1a8}
 .box{border:1px solid #1e2a26;border-radius:10px;padding:18px;margin-top:22px;max-width:70ch}
</style></head><body>
<h1>VishapHub</h1>
<p>Carries a request between the generator, the validator and the analyser.
The verdict belongs to the pipeline, not to the conversation.</p>
<div class="box">
 <div>GET <code>/health</code></div>
 <div>POST <code>/run</code> {"intent": "analyse", "material": "...", "iterations": 1}</div>
</div>
</body></html>
"""


def _plan_for(body: dict):
    intent = str(body.get("intent") or "").strip()
    if not intent:
        raise ValueError("intent is required: analyse | generate | validate | generate+validate+analyse")
    try:
        iterations = int(body.get("iterations") or 1)
    except (TypeError, ValueError):
        raise ValueError("iterations must be an integer")
    return plan_for(intent, iterations)


class Handler(BaseHTTPRequestHandler):
    server_version = f"vishap-hub/{__version__}"

    def _send(self, code: int, payload: dict | str, content_type: str = "application/json") -> None:
        body = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", content_type + "; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send(200, {"ok": True, "version": __version__})
        elif path in ("/", "/index.html"):
            self._send(200, INDEX, "text/html")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        if self.path.split("?", 1)[0] != "/run":
            self._send(404, {"error": "not found"})
            return

        length = int(self.headers.get("content-length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send(400, {"error": f"body must be 1..{MAX_BODY} bytes"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, {"error": "body must be JSON"})
            return
        if not isinstance(body, dict):
            self._send(400, {"error": "body must be a JSON object"})
            return

        try:
            plan = _plan_for(body)
        except (ValueError, RouteError) as exc:
            self._send(400, {"error": str(exc)})
            return

        result = run_plan(
            ServiceConfig(),
            plan,
            material=str(body.get("material") or ""),
            spec=str(body.get("spec") or ""),
            filename=str(body.get("filename") or "input.txt"),
            out_dir=str(body.get("out_dir") or ""),
            validator_spec=body.get("validator_spec") or {},
        )
        self._send(200 if result.ok else 502, {"plan": plan.as_dict(), "result": result.as_dict()})


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"vishap-hub {__version__} listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
