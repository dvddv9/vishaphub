"""HTTP face for the validator: `GET /health`, `POST /check`, `GET /`.

A deliverable arrives as JSON — a map of relative path to file text — because that is
what a generator can send and what a browser can build from a drop of files. Nothing
is written to disk outside a temp directory, and the temp directory is removed.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .engine import validate
from .models import Spec
from .version import __version__

MAX_BODY = 8_000_000
PAGE = os.path.join(os.path.dirname(__file__), "web", "index.html")


def _write_files(root: str, files: dict) -> None:
    for rel, text in files.items():
        if not isinstance(rel, str) or not isinstance(text, str):
            continue
        safe = os.path.normpath(rel).lstrip("\\/")
        if safe.startswith("..") or os.path.isabs(safe):
            continue  # a path that climbs out is not a deliverable, it is an attack
        target = os.path.join(root, safe)
        os.makedirs(os.path.dirname(target) or root, exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(text)


class Handler(BaseHTTPRequestHandler):
    server_version = f"vishap-validator/{__version__}"

    def _send(self, code: int, payload, content_type: str = "application/json") -> None:
        body = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", content_type + "; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # stdlib naming
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send(200, {"ok": True, "version": __version__})
        elif path in ("/", "/index.html"):
            if os.path.exists(PAGE):
                with open(PAGE, encoding="utf-8") as fh:
                    self._send(200, fh.read(), "text/html")
            else:
                self._send(500, {"error": "page missing from the image"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # stdlib naming
        if self.path.split("?", 1)[0] != "/check":
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
        if not isinstance(body, dict) or not isinstance(body.get("files"), dict):
            self._send(400, {"error": 'body must be {"files": {"path": "text"}, "spec": {...}}'})
            return

        raw_spec = body.get("spec") or {}
        if not isinstance(raw_spec, dict):
            self._send(400, {"error": "spec must be an object"})
            return
        known = {"language", "files", "exports", "tests", "entry"}
        unknown = set(raw_spec) - known
        if unknown:
            self._send(400, {"error": f"unknown spec keys: {', '.join(sorted(unknown))}"})
            return

        spec = Spec(
            language=raw_spec.get("language", "python"),
            files=list(raw_spec.get("files", [])),
            exports=list(raw_spec.get("exports", [])),
            tests=list(raw_spec.get("tests", [])),
            entry=raw_spec.get("entry", ""),
        )

        root = tempfile.mkdtemp(prefix="vishap-check-")
        try:
            _write_files(root, body["files"])
            report = validate(root, spec)
            payload = report.as_dict()
            code = 200 if payload["verdict"] in ("PASS", "NEEDS_REVIEW") else 422
            self._send(code, payload)
        finally:
            shutil.rmtree(root, ignore_errors=True)


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"vishap-validator {__version__} listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
