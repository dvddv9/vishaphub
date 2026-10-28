# API Reference

Base URL: **`http://localhost:8080`**

Most `/analyze*` endpoints accept an optional API key (`X-API-Key`) when `CONVEYOR_API_KEY` is set.

---

## `GET /health`

Liveness probe.

```
curl http://localhost:8080/health
```

```
{"status": "ok", "timestamp": "2026-10-22T12:00:00", "harness": {"url": "http://127.0.0.1:3080", "reachable": false}}
```

---

GET /llm/config

Returns the current LLM provider settings (API key is never exposed).

```
curl http://localhost:8080/llm/config
```

```
{
  "provider": "custom",
  "custom_url": "https://api.groq.com/openai/v1",
  "custom_model": "llama-3.3-70b-versatile",
  "has_custom_key": true
}
```

POST /llm/config

Change the LLM provider. Accepts provider (custom | anthropic | openai | groq | ollama | deepseek), and for custom — custom_url, custom_model, custom_key.

```
curl -X POST http://localhost:8080/llm/config \
  -H "Content-Type: application/json" \
  -d '{"provider": "custom", "custom_url": "https://api.groq.com/openai/v1", "custom_model": "llama-3.3-70b-versatile", "custom_key": "gsk_..."}'
```

```
{"status": "ok", "provider": "custom"}
```

---

POST /analyze

Run the full pipeline synchronously.

Auth: optional X-API-Key (when CONVEYOR_API_KEY is set)

```
curl -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -d '{"material": "def f(): pass", "filename": "x.py"}'
```

```
{
  "session_id": "sess-2026-10-22-120000",
  "filename": "x.py",
  "level": "D0",
  "final_markdown": "# D0 — f()\n...",
  "audit": {"material_hash": "sha256:...", "critique_verdict": "SAFE"}
}
```

Errors: 400 empty material, 500 pipeline error.

---

POST /analyze/async

Enqueue an analysis job (Celery + Redis; falls back to an in-process background task when the broker is unavailable).

Auth: optional X-API-Key

```
curl -X POST http://localhost:8080/analyze/async \
  -H "Content-Type: application/json" \
  -d '{"material": "def f(): pass", "filename": "x.py"}'
```

```
{"job_id": "job-abc123def456", "status": "queued"}
```

GET /status/`{job_id}`

```
curl http://localhost:8080/status/job-abc123def456
```

```
{
  "job_id": "job-abc123def456",
  "status": "done",
  "filename": "x.py",
  "created_at": "...",
  "started_at": "...",
  "finished_at": "...",
  "error": null
}
```

Errors: 404 job not found.

GET /report/`{job_id}`

```
curl http://localhost:8080/report/job-abc123def456
```

Returns the full result object.

Errors: 404 job not found, 409 job not done yet.

---

POST /analyze/secure

Clerk-authenticated variant of /analyze (multi-tenant).

Auth: `Authorization: Bearer <clerk-jwt>`

```
curl -X POST http://localhost:8080/analyze/secure \
  -H "Authorization: Bearer <clerk-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"material": "def f(): pass", "filename": "x.py"}'
```

Errors: 401 missing/invalid token.

---

POST /webhook/github

GitHub App webhook. On pull_request (opened) it analyzes the diff and posts a PR comment.

Auth: X-Hub-Signature-256 (HMAC, GITHUB_WEBHOOK_SECRET)

```json
{"ok": true, "triggered": true, "verdict": "REQUIRES_REVIEW"}
```

Errors: 403 invalid signature.

---

GET /metrics

Prometheus metrics (text/plain; version=0.0.4).

```
curl http://localhost:8080/metrics
```

```
