"""HTTP face for the hub: the assistant, the pipeline, and one page.

`GET /` is the page, `GET /health` the liveness probe, `POST /chat` the assistant,
`POST /run` the pipeline. Standard library only — the service must start in a second,
and a framework is not what makes routing correct.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import one
from .chat import reply
from .pipeline import run_plan
from .tts import available as tts_available, speak as tts_speak
from .router import RouteError, plan_for
from .version import __version__

MAX_BODY = 4_000_000
WEB = os.path.join(os.path.dirname(__file__), "web")
STATIC = {
    "/greeting.mp3": ("greeting.mp3", "audio/mpeg"),
}


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

    def _send(self, code: int, payload, content_type: str = "application/json") -> None:
        if isinstance(payload, bytes):
            body = payload
        elif isinstance(payload, str):
            body = payload.encode("utf-8")
        else:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if "text" in content_type or "json" in content_type:
            content_type = content_type + "; charset=utf-8"
        self.send_response(code)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send(200, {"ok": True, "version": __version__})
            return
        if path in STATIC:
            name, kind = STATIC[path]
            full = os.path.join(WEB, name)
            if os.path.exists(full):
                with open(full, "rb") as fh:
                    self._send(200, fh.read(), kind)
            else:
                self._send(404, {"error": "asset missing"})
            return
        if path in ("/", "/index.html"):
            page = os.path.join(WEB, "index.html")
            if os.path.exists(page):
                with open(page, encoding="utf-8") as fh:
                    self._send(200, fh.read(), "text/html")
            else:
                self._send(500, {"error": "page missing from the image"})
            return
        self._send(404, {"error": "not found"})

    def _body(self) -> dict | None:
        length = int(self.headers.get("content-length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send(400, {"error": f"body must be 1..{MAX_BODY} bytes"})
            return None
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, {"error": "body must be JSON"})
            return None
        if not isinstance(body, dict):
            self._send(400, {"error": "body must be a JSON object"})
            return None
        return body

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        path = self.path.split("?", 1)[0]

        if path == "/chat":
            body = self._body()
            if body is None:
                return
            message = body.get("message")
            if not isinstance(message, str) or not message.strip():
                self._send(400, {"ok": False, "error": "message is required"})
                return
            messages = body.get("messages") if isinstance(body.get("messages"), list) else []
            result = reply(message, messages, str(body.get("api_key") or ""), str(body.get("model") or ""))
            self._send(200 if result["ok"] else 502, result)
            return

        if path == "/speak":
            body = self._body()
            if body is None:
                return
            text = body.get("text")
            if not isinstance(text, str) or not text.strip():
                self._send(400, {"ok": False, "error": "text is required"})
                return
            if not tts_available():
                self._send(503, {"ok": False, "error": "speech is not installed in this image"})
                return
            audio = tts_speak(text)
            if not audio:
                self._send(502, {"ok": False, "error": "the voice produced no audio"})
                return
            self._send(200, audio, "audio/mpeg")
            return

        if path == "/run":
            body = self._body()
            if body is None:
                return
            spec_text = body.get("spec") if isinstance(body.get("spec"), str) else ""
            result = one.run(
                material=str(body.get("material") or ""),
                spec=spec_text,
                question=str(body.get("question") or ""),
                api_key=str(body.get("api_key") or ""),
                model=str(body.get("model") or ""),
            )
            self._send(200 if result.get("ok") else 502, result)
            return

        self._send(404, {"error": "not found"})


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"vishap-hub {__version__} listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
