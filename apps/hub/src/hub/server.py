"""HTTP face for the hub: the assistant, the pipeline, the runs, and one page.

`GET /` is the page, `GET /health` the liveness probe, `POST /chat` the assistant,
`POST /run` the pipeline, `POST /run/stream` the same run as server-sent events,
`GET /r/<id>` a run as a page, `GET /runs` the recent runs. Standard library only:
the service must start in a second, and a framework is not what makes routing correct.

Every door that spends something has a ceiling: a request budget per address for the
run, the chat and the voice, a length limit on the text, and a cache for the voice.
The same words are synthesised once, not once per visitor.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import fingerprint, limits, templates
from .chat import reply
from .pipeline import run_plan
from .router import RouteError, plan_for
from .store import RunStore
from .tts import VOICE, available as tts_available, speak as tts_speak
from .version import __version__

MAX_BODY = 4_000_000
WEB = os.path.join(os.path.dirname(__file__), "web")
#: filename, content type, and whether it may be cached for a while (fixed name, rarely changed)
STATIC = {
    "/styles.css": ("styles.css", "text/css", True),
    "/app.js": ("app.js", "application/javascript", True),
    "/favicon.svg": ("favicon.svg", "image/svg+xml", True),
    "/greeting.mp3": ("greeting.mp3", "audio/mpeg", True),
}
STATIC_MAX_AGE = "300"

LIMITERS = {kind: limits.RateLimiter(limits.per_minute(kind)) for kind in ("run", "chat", "speak")}
TTS_CACHE = limits.TTSCache(limits.int_env("VISHAP_HUB_TTS_CACHE", limits.DEFAULT_TTS_ITEMS))
RUNS = RunStore(keep=limits.int_env("VISHAP_HUB_RUNS_KEEP", 200),
                path=os.getenv("VISHAP_HUB_RUNS_FILE", ""))


class _ClientGone(Exception):
    """The streaming reader closed the connection; there is nobody to send to."""


#: Headers that cost nothing and close a class of attacks. The site check flags their
#: absence, so the site should not be the one that fails it.
SECURITY_HEADERS = {
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "content-security-policy": (
        "default-src 'self'; img-src 'self' data:; media-src 'self'; "
        "style-src 'self'; script-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
}


def _intent_for(body: dict, material: str, spec: str) -> str:
    """What the client asked for, inferred from what it sent when it did not say.

    An explicit `intent` always wins. Otherwise the request is read literally: a spec
    and material means build it and check it, a spec alone means build and validate, a
    material alone means look at it, and a bare question is for the model to answer.
    """
    explicit = str(body.get("intent") or "").strip()
    if explicit:
        return explicit
    if material.strip() and spec.strip():
        return "generate+validate+analyse"
    if spec.strip():
        return "generate+validate"
    if material.strip():
        return "analyse"
    return "ask"


class Handler(BaseHTTPRequestHandler):
    server_version = f"vishap-hub/{__version__}"

    # ---- plumbing -------------------------------------------------------

    def _send(self, code: int, payload, content_type: str = "application/json",
              extra: dict | None = None) -> None:
        if isinstance(payload, bytes):
            body = payload
        elif isinstance(payload, str):
            body = payload.encode("utf-8")
        else:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if "text" in content_type or "json" in content_type:
            content_type = content_type + "; charset=utf-8"
        self.send_response(code)
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _limited(self, kind: str) -> bool:
        allowed, wait = LIMITERS[kind].allow(self.client_address[0])
        if allowed:
            return False
        self._send(429, {"ok": False, "error": f"too many {kind} requests from this address"},
                   extra={"retry-after": str(int(wait) + 1)})
        return True

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

    def _remember(self, payload: dict, args: dict | None = None) -> None:
        """Keep the run, and give even a refused run an id: a failure is a result too."""
        fp = payload.get("fingerprint") or {}
        if not fp.get("id") and args:
            fp = fingerprint.of(
                material=args.get("material", ""),
                spec=args.get("spec"),
                files=args.get("files") or {},
                plan=payload.get("plan") or {},
                verdict=payload.get("verdict", "ERROR"),
                steps=payload.get("steps") or [],
            )
            payload["fingerprint"] = fp
        if not fp.get("id"):
            return
        RUNS.save({
            "id": fp["id"],
            "at": fp.get("at", ""),
            "verdict": payload.get("verdict"),
            "ok": payload.get("ok"),
            "plan": payload.get("plan"),
            "summary": payload.get("summary", ""),
            "result": payload,
        })

    # ---- GET ------------------------------------------------------------

    def _html(self, code: int, markup: str) -> None:
        self._send(code, markup, "text/html")

    def _static(self, path: str) -> bool:
        name, kind, cacheable = STATIC[path]
        full = os.path.join(WEB, name)
        if not os.path.exists(full):
            self._send(404, {"error": "asset missing"})
            return True
        with open(full, "rb") as fh:
            body = fh.read()
        extra = {"cache-control": f"public, max-age={STATIC_MAX_AGE}, must-revalidate"} if cacheable else {}
        self._send(200, body, kind, extra=extra)
        return True

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        path = self.path.split("?", 1)[0]

        # --- machine doors: JSON only, never a page
        if path == "/health":
            self._send(200, {"ok": True, "version": __version__})
            return
        if path == "/api/runs":
            self._send(200, {"runs": RUNS.list(20)})
            return
        if path.startswith("/api/runs/"):
            record = RUNS.get(path[len("/api/runs/"):].removesuffix(".json"))
            if record is None:
                self._send(404, {"error": "no such run, or it is older than the stored ones"})
                return
            self._send(200, record)
            return
        if path.startswith("/api/") or path == "/api":
            self._send(404, {"error": "not found"})
            return

        # --- pages
        if path in STATIC:
            self._static(path)
            return
        if path == "/runs":
            self._html(200, templates.runs_page(RUNS.list(20)))
            return
        if path.startswith("/r/") and len(path) > 3:
            record = RUNS.get(path[3:])
            if record is None:
                self._html(404, templates.message_page(
                    "No such run", "It is older than the runs this hub still keeps, or the link is wrong."))
                return
            self._html(200, templates.report_page(record))
            return
        if path in ("/", "/index.html"):
            page = os.path.join(WEB, "index.html")
            if os.path.exists(page):
                with open(page, encoding="utf-8") as fh:
                    self._send(200, fh.read(), "text/html",
                               extra={"cache-control": "no-cache"})
            else:
                self._send(500, {"error": "page missing from the image"})
            return
        self._html(404, templates.message_page("Not found", "There is nothing at this address."))

    # ---- POST -----------------------------------------------------------

    def _run_args(self, body: dict) -> dict | None:
        material = str(body.get("material") or "")
        spec_text = body.get("spec") if isinstance(body.get("spec"), str) else ""
        try:
            plan = plan_for(_intent_for(body, material, spec_text), int(body.get("iterations") or 1))
        except (RouteError, ValueError) as exc:
            self._send(400, {"ok": False, "error": f"cannot route: {exc}"})
            return None
        return {
            "plan": plan,
            "material": material,
            "files": body.get("files") if isinstance(body.get("files"), dict) else {},
            "spec": body.get("spec") if isinstance(body.get("spec"), dict) else spec_text,
            "question": str(body.get("question") or ""),
            "api_key": str(body.get("api_key") or ""),
            "model": str(body.get("model") or ""),
        }

    def _respond(self, result, args: dict | None = None) -> None:
        payload = result.as_dict()
        if not payload["ok"]:
            payload["error"] = payload.get("reason") or "the run did not pass its gates"
        self._remember(payload, args)
        self._send(200 if payload["ok"] else 502, payload)

    def _stream(self, args: dict) -> None:
        """The same run, announced stage by stage: a minute of silence reads as broken."""
        self.send_response(200)
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("x-accel-buffering", "no")
        self.end_headers()

        def event(name: str, payload: dict) -> None:
            try:
                self.wfile.write(f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                raise _ClientGone(str(exc)) from None

        try:
            result = run_plan(on_step=lambda stage, payload: event("stage", payload), **args)
        except _ClientGone:
            return
        except Exception as exc:  # noqa: BLE001 - reported to the client, never silent
            try:
                event("error", {"error": f"{type(exc).__name__}: {exc}"})
            except _ClientGone:
                return
            return
        payload = result.as_dict()
        if not payload["ok"]:
            payload["error"] = payload.get("reason") or "the run did not pass its gates"
        self._remember(payload, args)
        try:
            event("done", payload)
        except _ClientGone:
            return

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        path = self.path.split("?", 1)[0]

        if path == "/chat":
            body = self._body()
            if body is None:
                return
            if self._limited("chat"):
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
            if self._limited("speak"):
                return
            text = body.get("text")
            if not isinstance(text, str) or not text.strip():
                self._send(400, {"ok": False, "error": "text is required"})
                return
            ceiling = limits.tts_max_chars()
            if ceiling and len(text) > ceiling:
                self._send(413, {"ok": False, "error": f"text is longer than {ceiling} characters"})
                return
            if not tts_available():
                self._send(503, {"ok": False, "error": "speech is not installed in this image"})
                return
            key = limits.TTSCache.key(text, VOICE)
            cached = TTS_CACHE.get(key)
            if cached:
                self._send(200, cached, "audio/mpeg", extra={"x-tts-cache": "hit"})
                return
            audio = tts_speak(text)
            if not audio:
                self._send(502, {"ok": False, "error": "the voice produced no audio"})
                return
            TTS_CACHE.put(key, audio)
            self._send(200, audio, "audio/mpeg", extra={"x-tts-cache": "miss"})
            return

        if path in ("/run", "/run/stream"):
            body = self._body()
            if body is None:
                return
            if self._limited("run"):
                return
            args = self._run_args(body)
            if args is None:
                return
            if path == "/run/stream":
                self._stream(args)
                return
            self._respond(run_plan(**args), args)
            return

        self._send(404, {"error": "not found"})


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"vishap-hub {__version__} listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
