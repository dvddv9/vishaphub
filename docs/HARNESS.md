# Harness (DSH) Integration

> **Legacy.** Since v7.3.12 Vishap talks to any OpenAI-compatible endpoint (`CUSTOM_LLM_*`), Claude by default (see `.env.example`). DSH is optional and the `HARNESS_*` variables below are no longer read by the API. This page is kept for reference.


Vishap uses **DeepSeek Harness (DSH)** as its only LLM provider. There is no
direct DeepSeek API, no OpenAI-compatible endpoint and no Ollama — every stage
talks to a local harness, and material does not leave the machine.

## Requirements

- DSH installed (desktop app or the `@deepseek-ai/dsh` CLI).
- `dsh web` listening on port 3080:

```powershell
& "$env:LOCALAPPDATA\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd" web
```

- The token it prints: `http://127.0.0.1:3080/?token=<TOKEN>`.

## Configuration (`.env`)

```ini
HARNESS_URL=http://127.0.0.1:3080
HARNESS_TOKEN=<token from dsh web>
# HARNESS_TIMEOUT=30        # per-request timeout
# HARNESS_AUTOSTART=1       # start `dsh web` when it is not answering
# HARNESS_CMD=              # explicit path to the dsh CLI
```

## Autostart

The API starts a background thread at boot (`_start_harness_in_background` in
`src/main.py`). It:

1. tries every token it knows — `HARNESS_TOKEN`, the remembered one in
   `harness-token.txt`, and the one in `logs/harness-spawn.log` — and uses the
   first that answers `200`;
2. if none does, locates the `dsh` CLI (`HARNESS_CMD` → `PATH` → the DSH install
   path) and spawns `dsh web --no-open` **detached**, with its output going to
   `logs/harness-spawn.log`;
3. reads the **one-time token** DSH prints there, remembers it in
   `harness-token.txt`, and probes until it answers (up to 30 s);
4. if the port is held by a harness whose token we never saw (`HTTP 401` on every
   candidate), it stops that listener and starts a fresh harness — `dsh web`
   issues a new token on every start, so a restart is the only recovery;
5. logs `[harness] ready at ...` or `[harness] not reachable: ...`.

It never delays API startup, never raises, and **refuses to start a harness for a
non-loopback `HARNESS_URL`** — starting a process on someone else's host is not
its job. Disable it with `HARNESS_AUTOSTART=0` (the right setting on a shared
server). It is skipped under pytest.

`--no-open` matters in the desktop app: without it every start pops a browser tab
on top of the app window.

## Health

`GET /health` now answers:

```json
{
  "status": "ok",
  "timestamp": "2026-10-19T17:38:06",
  "harness": {
    "url": "http://127.0.0.1:3080",
    "reachable": false,
    "started": false,
    "command": "C:\\Users\\<user>\\AppData\\Local\\Programs\\DeepSeek Harness\\...\\dsh.cmd",
    "autostart": true,
    "error": "HARNESS_TOKEN empty"
  }
}
```

The snapshot is cached and re-probed every 10 s (`STATUS_TTL`), so the endpoint
stays instant — the desktop readiness loop hits it every few hundred milliseconds.

Command-line check:

```bash
python -m src.llm.harness_launcher     # exit 0 when reachable, 1 otherwise
```

### Endpoints and the UI badge

| Endpoint | Behaviour |
| --- | --- |
| `GET /harness/status` | fresh probe, 0.3 s timeout — what the badge polls |
| `POST /harness/start` | `202` immediately, runs `ensure_harness()` in the background; errors are logged, never returned |
| `GET /health` | `harness` block (cached, re-probed every 10 s) |

`ui-next/src/components/HarnessBadge.tsx` sits in the navbar on every page and
polls `/harness/status` (15 s idle, 1.5 s while starting). When the harness is
down it shows `Harness off` and a **Start** button that calls
`POST /harness/start`; the badge flips to `Harness` as soon as the probe answers.
If the API itself is unreachable it shows `API` instead — the harness must not be
blamed for a dead backend. Starting gives up after 40 s, at which point the tooltip
carries `HARNESS_TOKEN empty` / `dsh CLI not found` and the log has the detail.

## How it works

1. `client.chat()` / `async_chat()` → `HarnessClient`.
2. `HarnessClient.chat(user, system)`:
   - `GET /?token=...` — sets the `dsh-auth-*` cookie;
   - `POST /api/session/create` — new session with `cwd`;
   - `POST /api/session/prompt` — UTF-8 prompt, `mode=queue`;
   - polls `~/.dsh/sessions/<slug>/<sid>/session.v4.jsonl.zstd` for the reply.
3. Returns `{"text": ..., "model": "harness", "mode": "harness"}`.

Async wraps the sync client in `loop.run_in_executor`. The harness owns model
selection and sampling: `temperature` / `max_tokens` are accepted by `chat()` for
interface compatibility and are not forwarded.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `HARNESS_URL` | `http://127.0.0.1:3080` | DSH web endpoint |
| `HARNESS_TOKEN` | — | auth token from `dsh web` |
| `HARNESS_TIMEOUT` | `30` | per-request timeout (seconds) |
| `HARNESS_AUTOSTART` | `1` | start `dsh web` when it is not answering |
| `HARNESS_CMD` | — | explicit path to the `dsh` CLI |
| `VISHAP_DATA_DIR` | `~/.vishap/data` | `mode.json` location |

## Timeouts

`POLL_TIMEOUT = 600` s in `harness_client.py`; large files take 3–5 min. The HTTP
calls themselves use `HARNESS_TIMEOUT` (30 s).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `401 auth failed` | `HARNESS_TOKEN` is stale — restart `dsh web` and update `.env` |
| `HARNESS_TOKEN empty` | the token was never copied; see `dsh web` output |
| `timeout waiting for reply` | increase `POLL_TIMEOUT`, or check the model in DSH is alive |
| `harness is remote (…); not starting it` | `HARNESS_URL` points elsewhere — start that harness yourself |
| `cannot autostart - dsh CLI not found` | set `HARNESS_CMD` to the `dsh` path |
| `PermissionError ~/.vishap/data` | set `VISHAP_DATA_DIR` |

## Limitations

- DSH is a developer preview; the RPC format may change.
- `session.v4.jsonl.zstd` is versioned; a DSH update may rename it.
- There is no second provider to fall back to (by design since v7.0.0).

## Files

- `src/llm/harness_client.py` — transport: sessions, prompts, log polling.
- `src/llm/harness_launcher.py` — locate, probe, autostart, cached status.
- `src/llm/client.py` / `async_client.py` — the only entry points.
- `src/storage/mode.py` — `VALID_MODES = ("harness",)`.
