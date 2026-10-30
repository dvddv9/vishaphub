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
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from . import access, alerts, demo, fingerprint, limits, meter, templates
from .chat import reply
from .pipeline import run_plan
from .router import RouteError, plan_for
from .store import RunStore, owner_key
from .teamstore import DEFAULT_RETENTION_DAYS, Denied, TeamStore
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


def _init_teams() -> TeamStore | None:
    """Team mode is on when VISHAP_HUB_DATABASE_URL is set; otherwise nothing of it is loaded."""
    url = os.getenv("VISHAP_HUB_DATABASE_URL", "")
    if not url:
        return None
    return TeamStore(url, limits.int_env("VISHAP_HUB_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))


TEAMS = _init_teams()
ALERTS = alerts.from_env()
#: with this on, /run, /chat and /speak refuse a caller who has no API key (the setting for a pilot)
REQUIRE_KEY = os.getenv("VISHAP_HUB_REQUIRE_KEY", "").lower() in ("1", "true", "yes")
KEY_COOKIE_MAX_AGE = 30 * 24 * 3600


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

    def _drain(self) -> None:
        """Read and drop a request body nobody asked for before replying, once.

        A refusal that is sent while the client is still writing its body is not delivered on Windows
        (WinError 10053) and can reset the connection elsewhere: the client sees a dead socket, not the 401.
        """
        if getattr(self, "_body_taken", False):
            return
        self._body_taken = True
        try:
            length = int(self.headers.get("content-length") or 0)
        except ValueError:
            return
        if 0 < length <= MAX_BODY:
            self.rfile.read(length)

    def _send(self, code: int, payload, content_type: str = "application/json",
              extra: dict | None = None) -> None:
        self._drain()
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

    def _principal(self):
        """(principal, refused). principal is None for an anonymous caller. refused is True when a reply
        was already sent: the caller presented a key, and it is wrong, revoked, or team mode is off."""
        creds = access.credentials(self.headers)
        if creds is None:
            return None, False
        kind, token = creds
        if kind != "key" or TEAMS is None:
            self._refuse_key("an API key was sent but it is not valid here")
            return None, True
        try:
            principal = TEAMS.authenticate(token)
        except Exception as exc:  # noqa: BLE001 - the database is down: say so, do not guess
            print(f"team storage error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            self._send(503, {"error": "team storage is unavailable"})
            return None, True
        if principal is None:
            self._refuse_key("invalid or revoked API key")
            return None, True
        return principal, False

    def _refuse_key(self, message: str) -> None:
        if self.path.startswith("/api/") or self.command != "GET":
            self._send(401, {"error": message}, extra=PRIVATE)
        else:
            self._html(401, templates.message_page("Not signed in", f"{message}. Sign in at /login."), extra=PRIVATE)

    def _spender(self):
        """The caller of a door that spends (/run, /chat, /speak): (principal, refused)."""
        principal, refused = self._principal()
        if refused:
            return None, True
        if principal is None:
            if REQUIRE_KEY:
                self._send(401, {"error": "an API key is required"}, extra=PRIVATE)
                return None, True
            return None, False
        if not principal.can("run.create"):
            self._send(403, {"error": "your role may read, not run, chat or speak"}, extra=PRIVATE)
            return None, True
        return principal, False

    def _team(self, fn, *args):
        """Call the team store; a failure is a 503 that says so, never a silent empty answer."""
        try:
            return True, fn(*args)
        except Exception as exc:  # noqa: BLE001
            print(f"team storage error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            self._send(503, {"error": "team storage is unavailable"})
            return False, None

    def _reserve(self, principal, kind: str, chars: int) -> bool:
        """Take one request from the person's, the team's and the hub's allowance before any work is done.
        False means a reply was sent: 429 with the scope that is spent and when the window frees up."""
        ok, res = self._team(TEAMS.reserve, principal, kind, chars, self.client_address[0])
        if not ok:
            return False
        if isinstance(res, Denied):
            scope = {"user": f"quota:user:{principal.user_id}:{kind}", "team": f"quota:team:{principal.team_id}:{kind}",
                     "global": f"global:{kind}"}[res.scope]
            ALERTS.check(scope, res.used, res.limit, f"{res.scope} {kind} requests")
            self._send(429, {"ok": False, "error": res.message, "scope": res.scope, "limit": res.limit},
                       extra={"retry-after": str(res.retry_after), **PRIVATE})
            return False
        for scope, used, limit, label in res.counts:
            ALERTS.check(scope, used, limit, label)
        self._usage = {"id": res.usage_id, "chars": chars, "done": False, "principal": principal}
        return True

    def _finish_usage(self, run_id: str | None = None, result_chars: int = 0, outcome: str = "error") -> None:
        """Write down what the request cost, once. The first caller wins: a normal end, else the safety net."""
        usage = getattr(self, "_usage", None)
        if not usage or usage["done"]:
            return
        usage["done"] = True
        try:
            TEAMS.finish(usage["principal"], usage["id"], run_id, usage["chars"], result_chars,
                         getattr(self, "_meter", None), outcome)
        except Exception as exc:  # noqa: BLE001 - the books are late, the answer is not
            print(f"usage not recorded: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    def _form(self) -> dict | None:
        self._body_taken = True
        length = int(self.headers.get("content-length") or 0)
        if length <= 0 or length > 4096:
            self._send(400, {"error": "form must be 1..4096 bytes"})
            return None
        return {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode("utf-8", "replace")).items()}

    def _limited(self, kind: str) -> bool:
        allowed, wait = LIMITERS[kind].allow(self.client_address[0])
        if allowed:
            return False
        self._send(429, {"ok": False, "error": f"too many {kind} requests from this address"},
                   extra={"retry-after": str(int(wait) + 1)})
        return True

    def _body(self) -> dict | None:
        self._body_taken = True
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

    def _remember(self, payload: dict, args: dict | None = None, owner: str = "", principal=None) -> None:
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
        input_chars = limits.input_chars(args or {})
        result_chars = len(json.dumps(payload, ensure_ascii=False, default=str))
        record = {
            "id": fp["id"],
            "at": fp.get("at", ""),
            "verdict": payload.get("verdict"),
            "ok": payload.get("ok"),
            "plan": payload.get("plan"),
            "summary": payload.get("summary", ""),
            "result": payload,
            #: sizes in characters; the tokens the provider reported (None if it reported none); and an estimate
            "cost": meter.cost_of(getattr(self, "_meter", None), input_chars, result_chars),
            "owners": [owner] if owner else [],
            "demo": bool(args) and demo.is_demo(args),
        }
        if principal is None:
            RUNS.save(record)
            return
        self._finish_usage(fp["id"], result_chars, "ok" if payload.get("ok") else "failed")
        try:
            TEAMS.save(principal, record, self.client_address[0])
            payload["stored"] = True
        except Exception as exc:  # noqa: BLE001 - the run happened and was paid for: tell the caller it was not kept
            print(f"team storage error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            payload["stored"] = False

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
        principal, ip = None, self.client_address[0]
        if path.startswith(("/api/", "/runs", "/r/")):
            principal, refused = self._principal()
            if refused:
                return
        if path == "/api/me":
            if principal is None:
                self._send(401, {"error": "an API key is required"}, extra=PRIVATE)
                return
            self._send(200, {"team_id": principal.team_id, "user": principal.user_name, "role": principal.role,
                             "retention_days": TEAMS.retention_days(principal),
                             "permissions": sorted(access.PERMISSIONS[principal.role])}, extra=PRIVATE)
            return
        if path == "/api/team/audit":
            if principal is None:
                self._send(401, {"error": "an API key is required"}, extra=PRIVATE)
                return
            if not principal.can("audit.read"):
                self._send(403, {"error": "only an owner reads the audit trail"}, extra=PRIVATE)
                return
            query = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
            try:
                limit = int((query.get("limit") or ["100"])[0])
                before = int(query["before"][0]) if query.get("before") else None
            except ValueError:
                self._send(400, {"error": "limit and before must be integers"})
                return
            ok, events = self._team(TEAMS.audit_events, principal, limit, before)
            if ok:
                self._send(200, {"events": events}, extra=PRIVATE)
            return
        if path == "/api/runs" and principal is not None:
            ok, runs = self._team(TEAMS.list, principal, 20, ip)
            if ok:
                self._send(200, {"runs": runs}, extra=PRIVATE)
            return
        if path == "/api/runs":
            token = self._token()
            if token is None:
                self._send(403, {"error": "no owner: make a run from this browser first, "
                                          f"or send the {OWNER_HEADER} header you made it with"}, extra=PRIVATE)
                return
            self._send(200, {"runs": RUNS.list_for(owner_key(token), 20)}, extra=PRIVATE)
            return
        if path.startswith("/api/runs/") and principal is not None:
            run_id = path[len("/api/runs/"):].removesuffix(".json")
            ok, record = self._team(TEAMS.get, principal, run_id, ip)
            if not ok:
                return
            record = record or RUNS.get_for(run_id, None)             # the page's own example is public
            if record is None:
                self._send(404, {"error": "no such run in your team, or it has expired"}, extra=PRIVATE)
                return
            self._send(200, record, extra=PRIVATE)
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
        if path == "/login":
            self._html(200, templates.login_page(), extra=PRIVATE)
            return
        if path == "/runs" and principal is not None:
            ok, runs = self._team(TEAMS.list, principal, 20, ip)
            if ok:
                self._html(200, templates.runs_page(runs), extra=PRIVATE)
            return
        if path == "/runs":
            token = self._token()
            if token is None:
                self._html(403, templates.message_page(
                    "Runs are private",
                    "A run is listed only for the browser that made it, or for a signed-in team (/login). "
                    "Make a run here and it will appear."),
                    extra=PRIVATE)
                return
            self._html(200, templates.runs_page(RUNS.list_for(owner_key(token), 20)), extra=PRIVATE)
            return
        if path.startswith("/r/") and len(path) > 3 and principal is not None:
            ok, record = self._team(TEAMS.get, principal, path[3:], ip)
            if not ok:
                return
            if record is not None:
                self._html(200, templates.report_page(record, TEAMS.retention_note(principal)), extra=PRIVATE)
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
            self._html(200, templates.report_page(record, RUNS.retention()), extra=PRIVATE)
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

    def _respond(self, result, args: dict | None = None, owner: str = "", extra: dict | None = None,
                 principal=None) -> None:
        payload = result.as_dict()
        if not payload["ok"]:
            payload["error"] = payload.get("reason") or "the run did not pass its gates"
        self._remember(payload, args, owner, principal)
        self._send(200 if payload["ok"] else 502, payload, extra=extra)

    def _stream(self, args: dict, owner: str = "", extra: dict | None = None, principal=None) -> None:
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
        self._remember(payload, args, owner, principal)
        try:
            event("done", payload)
        except _ClientGone:
            return

    def do_POST(self) -> None:  # stdlib naming
        path = self.path.split("?", 1)[0]

        if path == "/login":
            form = self._form()
            if form is None:
                return
            key = (form.get("key") or "").strip()
            creds = access.credentials({"x-vishap-key": key})
            principal = None
            if TEAMS is not None and creds and creds[0] == "key":
                try:
                    principal = TEAMS.authenticate(creds[1])
                except Exception as exc:  # noqa: BLE001
                    print(f"team storage error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                    self._send(503, {"error": "team storage is unavailable"})
                    return
            if principal is None:
                self._html(401, templates.login_page("That key is not valid."), extra=PRIVATE)
                return
            cookie = (f"{access.KEY_COOKIE}={key}; Path=/; HttpOnly; SameSite=Lax; Max-Age={KEY_COOKIE_MAX_AGE}"
                      + ("; Secure" if (self.headers.get("x-forwarded-proto") or "").lower() == "https" else ""))
            self._send(303, b"", "text/plain", extra={"location": "/runs", "set-cookie": cookie, **PRIVATE})
            return
        if path == "/logout":
            self._send(303, b"", "text/plain", extra={
                "location": "/login", **PRIVATE,
                "set-cookie": f"{access.KEY_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"})
            return

        if path == "/chat":
            principal, refused = self._spender()
            if refused:
                return
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
            if principal is not None and not self._reserve(principal, "chat", len(message)):
                return
            with meter.metering() as m:
                self._meter = m
                try:
                    result = reply(message, messages, str(body.get("api_key") or ""), str(body.get("model") or ""))
                finally:
                    self._finish_usage(None, 0, "error")           # a no-op once the normal end below has run
            self._send(200 if result["ok"] else 502, result)
            return

        if path == "/speak":
            principal, refused = self._spender()
            if refused:
                return
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
            if principal is not None and not self._reserve(principal, "speak", len(text)):
                return
            try:
                audio = tts_speak(text)
            finally:
                self._finish_usage(None, 0, "error")
            if not audio:
                self._send(502, {"ok": False, "error": "the voice produced no audio"})
                return
            TTS_CACHE.put(key, audio)
            self._send(200, audio, "audio/mpeg", extra={"x-tts-cache": "miss"})
            return

        if path in ("/run", "/run/stream"):
            principal, refused = self._spender()
            if refused:
                return
            body = self._body()
            if body is None:
                return
            if self._limited("run"):
                return
            args = self._run_args(body)
            if args is None:
                return
            chars = limits.input_chars(args)
            if principal is None:
                spend = BUDGET.take(chars)
                if not spend.allowed:
                    self._send(413 if spend.too_big else 429, {"ok": False, "error": spend.reason},
                               extra={} if spend.too_big else {"retry-after": str(int(spend.wait) + 1)})
                    return
                used = BUDGET.used()
                ALERTS.check("anonymous:runs", used["runs"], BUDGET.runs, "anonymous runs")
                ALERTS.check("anonymous:chars", used["chars"], BUDGET.chars, "anonymous run characters")
            elif not self._reserve(principal, "run", chars):
                return
            owner, cookie = ("", {}) if principal is not None else self._owner_for_run()
            with meter.metering() as m:
                self._meter = m
                try:
                    if path == "/run/stream":
                        self._stream(args, owner, cookie, principal)
                        return
                    self._respond(run_plan(**args), args, owner, cookie, principal)
                finally:
                    self._finish_usage(None, 0, "error")           # a no-op once _remember has run
            return

        self._send(404, {"error": "not found"})


    def do_DELETE(self) -> None:  # stdlib naming
        path = self.path.split("?", 1)[0]
        if not path.startswith("/api/runs/"):
            self._send(404, {"error": "not found"})
            return
        principal, refused = self._principal()
        if refused:
            return
        if principal is None:
            self._send(401, {"error": "an API key is required to delete a run"}, extra=PRIVATE)
            return
        ok, outcome = self._team(TEAMS.delete, principal, path[len("/api/runs/"):].removesuffix(".json"),
                                 self.client_address[0])
        if not ok:
            return
        if outcome == "deleted":
            self._send(200, {"deleted": True}, extra=PRIVATE)
        elif outcome == "forbidden":
            self._send(403, {"error": "only an owner, or the person who made the run, may delete it"}, extra=PRIVATE)
        else:
            self._send(404, {"error": "no such run in your team, or it has expired"}, extra=PRIVATE)


def _purge_loop(minutes: int) -> None:
    """Remove expired runs now and then. Reads already ignore them; this is what frees the rows."""
    import time

    while True:
        try:
            removed = TEAMS.purge_expired()
            if removed:
                print(f"retention: removed {removed} expired run(s)", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"retention purge failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        time.sleep(max(1, minutes) * 60)


def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    if TEAMS is not None:
        threading.Thread(target=_purge_loop, args=(limits.int_env("VISHAP_HUB_PURGE_MINUTES", 60),),
                         daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"vishap-hub {__version__} listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
