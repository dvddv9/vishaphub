![Vishap Dragon](assets/icon.png)

# Vishap Security Analyzer for DeepSeek Harness

A DeepSeek Harness tool plugin that brings **Vishap** — a 6-stage security analysis pipeline — directly into your DSH chat.

## 🛡️ What it does

When you ask DSH to analyze code, configs, or logs for security risks, this plugin sends the material to a local Vishap backend. Vishap then runs it through its SAST/SCA rules and an LLM to produce a structured report:

- **Critical risks** (SQLi, XSS, RCE, path traversal, etc.) with CWE IDs and CVSS scores.
- **STRIDE threat model**.
- **Actionable fixes** (parameterized queries, input validation, etc.).
- **Audit trail** with SHA-256 provenance.

## 🚀 Quick Start

### 1. Prerequisites

- The **Vishap checkout** this package lives in, with its `.venv` ready. The plugin starts
  the backend itself on demand, so nothing has to be running beforehand.
- **DeepSeek Harness** (DSH) installed.

### 2. Install the plugin

This package sits at `dsh-plugin/` inside the Vishap repository. Point the DSH profile at
that directory:

```json
"my-dsh-plugin": "link:C:/AI/conveyor_app/dsh-plugin"
```

then run `pnpm install` in `$DSH_HOME/profiles/<profile>` and add the bundle to the
profile's `dsh.profile.bundles` list.

### 3. Use it

In DSH chat:
> Use vishap_analyze to analyze: `db.execute(f"SELECT * FROM users WHERE name = '{name}'")`

The plugin will return a full security report.

## ⚙️ Configuration

Everything is configurable from the dsh profile patch — no rebuild needed:

```yaml
- id: my-dsh-plugin
  name: my-dsh-plugin
  config:
    baseUrl: "http://127.0.0.1:5001"   # or $VISHAP_URL
    apiKeyEnv: "CONVEYOR_API_KEY"       # credential name, never the value
    autoStart: true                     # spawn the backend when /health is silent
    startCwd: "C:/AI/conveyor_app"      # Vishap checkout, or $VISHAP_HOME
    startTimeoutMs: 90000               # wait for /health after spawning
    replaceRunning: true                # take the port over from an older instance
    stopWhenDone: true                  # stop the backend this plugin started
    timeoutMs: 120000                   # per-call budget
    retries: 2                          # extra attempts on 5xx / connection errors
    maxBytes: 2097152                   # reject oversized material
    cacheTtlMs: 600000                  # local cache, keyed by filename + material hash
```

| Option | Default | Meaning |
|---|---|---|
| `baseUrl` | `$VISHAP_URL` → `http://127.0.0.1:5001` | Backend root |
| `apiKeyEnv` | `CONVEYOR_API_KEY` | Credential name resolved through the harness credential store, then the environment. The value is sent as `X-API-Key`; when it resolves to nothing, no header is sent |
| `autoStart` | `true` | Probe `/health` before every call and spawn the backend when it does not answer |
| `startCwd` | `$VISHAP_HOME` | Directory the backend is started in (its `.env` and `.venv` are read from here) |
| `startCommand` | `<startCwd>/.venv/.../python -m src.main` | Explicit `[executable, ...args]` when the default does not fit |
| `startTimeoutMs` | `60000` | How long to wait for `/health` after spawning; also added to the harness deadline |
| `replaceRunning` | `true` | A Vishap instance the plugin did not start is stopped and replaced. Identification goes through `/openapi.json`, so a stranger on the port is never killed |
| `stopWhenDone` | `true` | The backend this plugin started is stopped once the last in-flight call finishes |
| `timeoutMs` | `120000` | Budget for one call; the harness deadline is set 15 s above it |
| `retries` | `2` | Extra attempts; 4xx is never retried |
| `maxBytes` | `2097152` | Larger material is rejected before the request is sent |
| `cacheTtlMs` | `600000` | In-process cache; identical material returns instantly |

Behaviour worth knowing:

- **The plugin owns the backend lifecycle.** On each call it probes `GET /health`. If nothing
  answers it spawns `python -m src.main` in `startCwd` (output appended to
  `<startCwd>/_dsh-backend.log`) and polls `/health` until the deadline; a backend that exits
  during startup is reported together with the tail of that log. If something answers but the
  plugin did not start it — a stale console, an orphan after a harness restart — it confirms
  the identity through `/openapi.json` and stops that process before starting its own
  (`replaceRunning`). When the last in-flight call finishes, its own process is stopped
  (`stopWhenDone`), so nothing lingers on the port. Startup therefore costs one boot per
  call — roughly 30 s before the analysis begins.
- **No startup failure.** The key is resolved per call, so a missing key never stops the
  plugin from activating — it surfaces as a clear tool error instead.
- **Cancellation is forwarded.** `exec.signal` is fused with the timeout, so a cancelled
  call stops at the network layer instead of running to completion.
- **`filename` is validated** (`^[\w.-]{1,64}$`) because it is embedded in the analysis
  prompt; anything else is rejected to rule out prompt injection.
- **Local cache** keyed by `filename:sha256(material)`, so re-analyzing the same input is
  instant.

## 📄 License

MIT
