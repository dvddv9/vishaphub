"""HTTP face for the hub: the assistant, the pipeline, the runs, and one page.

`GET /` is the page, `GET /health` the liveness probe, `POST /chat` the assistant,
`POST /run` the pipeline, `POST /run/stream` the same run as server-sent events,
`GET /r/<id>` a run as a page, `GET /runs` the recent runs. Standard library only:
the service must start in a second, and a framework is not what makes routing correct.

A run belongs to whoever made it. The first `/run` hands the browser a random token in a
cookie (an API client may send it as `x-vishap-owner` instead); the store keeps only its
hash. The list of runs needs a token (403 without one) and shows only that token's runs;
a run opened by id is a 404 for anyone else - the same 404 as a run that never existed,
so the id proves nothing. The page's own example (`demo.py`) is the one public run.

Every door that spends something has a ceiling: a request budget per address for the
run, the chat and the voice, a length limit on the text, and a cache for the voice.
The same words are synthesised once, not once per visitor. A run also draws on a budget
for the whole process (runs and characters a day): when it is spent, `/run` says 429 and
why, and `/health` still answers. Each kept run records what it was sent and what came back.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import demo, fingerprint, limits, templates
from .chat import reply
from .pipeline import run_plan
from .router import RouteError, plan_for
from .store import RunStore, owner_key
from .tts import VOICE
from .tts import available as tts_available
from .tts import speak as tts_speak
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

OWNER_COOKIE = "vishap_owner"
OWNER_HEADER = "x-vishap-owner"
OWNER_COOKIE_MAX_AGE = 30 * 24 * 3600
_TOKEN = re.compile(r"[A-Za-z0-9_-]{24,128}")
#: what a private answer must not be: kept by a proxy or a shared cache
PRIVATE = {"cache-control": "private, no-store"}

LIMITERS = {kind: limits.RateLimiter(limits.per_minute(kind)) for kind in ("run", "chat", "speak")}
BUDGET = limits.RunBudget(limits.global_runs_per_day(), limits.global_chars_per_day())
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

    # ---- who is asking --------------------------------------------------

    def _token(self) -> str | None:
        """The owner token the client presented: the header first, then the cookie.

        None when there is none or it is malformed. The address is not an identity: it is
        shared by everyone behind one NAT, and the key in a run's body is the client's
        model key, not a name.
        """
        candidate = (self.headers.get(OWNER_HEADER) or "").strip()
        if not candidate:
            for part in (self.headers.get("cookie") or "").split(";"):
                name, _, value = part.strip().partition("=")
                if name == OWNER_COOKIE:
                    candidate = value.strip()
                    break
        return candidate if _TOKEN.fullmatch(candidate) else None

    def _owner_for_run(self) -> tuple[str, dict]:
        """The owner of the run about to be made, and the headers that give a new browser its token."""
        token = self._token()
        if token:
            return owner_key(token), {}
        token = secrets.token_urlsafe(24)
        cookie = f"{OWNER_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={OWNER_COOKIE_MAX_AGE}"
        if (self.headers.get("x-forwarded-proto") or "").lower() == "https":
            cookie += "; Secure"
        return owner_key(token), {"set-cookie": cookie}

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

    def _remember(self, payload: dict, args: dict | None = None, owner: str = "") -> None:
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
            "cost": {
                "input_chars": limits.input_chars(args or {}),
                #: size of what came back - a proxy for the model's output, which the hub does not meter
                "result_chars": len(json.dumps(payload, ensure_ascii=False, default=str)),
            },
            "owners": [owner] if owner else [],
            "demo": bool(args) and demo.is_demo(args),
        })

    # ---- GET ------------------------------------------------------------

    def _html(self, code: int, markup: str, extra: dict | None = None) -> None:
        self._send(code, markup, "text/html", extra=extra)

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

    def do_GET(self) -> None:  # stdlib naming
        path = self.path.split("?", 1)[0]

        # --- machine doors: JSON only, never a page
        if path == "/health":
            self._send(200, {"ok": True, "version": __version__})
            return
        if path == "/api/runs":
            token = self._token()
            if token is None:
                self._send(403, {"error": "no owner: make a run from this browser first, "
                                          f"or send the {OWNER_HEADER} header you made it with"}, extra=PRIVATE)
                return
            self._send(200, {"runs": RUNS.list_for(owner_key(token), 20)}, extra=PRIVATE)
            return
        if path.startswith("/api/runs/"):
            token = self._token()
            record = RUNS.get_for(path[len("/api/runs/"):].removesuffix(".json"),
                                  owner_key(token) if token else None)
            if record is None:
                self._send(404, {"error": "no such run, or it is not yours, or it is older than the stored ones"},
                           extra=PRIVATE)
                return
            self._send(200, record, extra=PRIVATE)
            return
        if path.startswith("/api/") or path == "/api":
            self._send(404, {"error": "not found"})
            return

        # --- pages
        if path in STATIC:
            self._static(path)
            return
        if path == "/runs":
            token = self._token()
            if token is None:
                self._html(403, templates.message_page(
                    "Runs are private",
                    "A run is listed only for the browser that made it. Make a run here and it will appear."),
                    extra=PRIVATE)
                return
            self._html(200, templates.runs_page(RUNS.list_for(owner_key(token), 20)), extra=PRIVATE)
            return
        if path.startswith("/r/") and len(path) > 3:
            token = self._token()
            record = RUNS.get_for(path[3:], owner_key(token) if token else None)
            if record is None:
                self._html(404, templates.message_page(
                    "No such run",
                    "No run with this id is open to you: it may be older than the runs this hub keeps, "
                    "the link may be wrong, or it may belong to someone else."), extra=PRIVATE)
                return
            self._html(200, templates.report_page(record), extra=PRIVATE)
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

    def _respond(self, result, args: dict | None = None, owner: str = "", extra: dict | None = None) -> None:
        payload = result.as_dict()
        if not payload["ok"]:
            payload["error"] = payload.get("reason") or "the run did not pass its gates"
        self._remember(payload, args, owner)
        self._send(200 if payload["ok"] else 502, payload, extra=extra)

    def _stream(self, args: dict, owner: str = "", extra: dict | None = None) -> None:
        """The same run, announced stage by stage: a minute of silence reads as broken."""
        self.send_response(200)
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("x-accel-buffering", "no")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
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
        self._remember(payload, args, owner)
        try:
            event("done", payload)
        except _ClientGone:
            return

    def do_POST(self) -> None:  # stdlib naming
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
            spend = BUDGET.take(limits.input_chars(args))
            if not spend.allowed:
                self._send(413 if spend.too_big else 429, {"ok": False, "error": spend.reason},
                           extra={} if spend.too_big else {"retry-after": str(int(spend.wait) + 1)})
                return
            owner, cookie = self._owner_for_run()
            if path == "/run/stream":
                self._stream(args, owner, cookie)
                return
            self._respond(run_plan(**args), args, owner, cookie)
            return

        self._send(404, {"error": "not found"})


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"vishap-hub {__version__} listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
