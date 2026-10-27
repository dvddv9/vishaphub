# Deployment

Vishap is distributed through **PyPI** and runs as a plain Python service under
**systemd**. Docker support (Dockerfile, Compose files, image workflows) was removed
in v7 — one install path, one process manager.

| Path | Use it for |
| --- | --- |
| `pip install vishap-analyzer` + `vishap analyze` | CLI, CI, one-off analysis |
| `python -m src.main` + systemd unit | a long-running API |
| `docker compose up -d api` (repo root) | a reproducible API image; the model stays on the host |
| Tauri desktop app | a local, single-user install |

---

## Production VPS (systemd)

Full walkthrough: [docs/VPS-DEPLOY.md](../docs/VPS-DEPLOY.md). Short version:

```bash
adduser --system --group --home /opt/conveyor_app conveyor
git clone https://github.com/dvddv9/vishap.git /opt/conveyor_app
cd /opt/conveyor_app
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env          # DATABASE_URL, CONVEYOR_API_KEY, keys
.venv/bin/alembic upgrade head
cp deploy/systemd/vishap.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now vishap
curl -fsS http://127.0.0.1:5001/health
```

Put a TLS terminator in front (`127.0.0.1:5001` is the only port the app binds when
`CONVEYOR_API_KEY` is set):

```
api.example.com {
    reverse_proxy 127.0.0.1:5001
}
```

## Local run (no containers)

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # set HARNESS_URL + HARNESS_TOKEN
python -m src.main          # API on :5001, docs at /docs
```

Postgres and Redis are only needed for the multi-tenant paths and the
async job store; `JOB_STORE=memory` runs the API without them.

## Env vars

| Var | Default | Required |
| --- | --- | --- |
| `DATABASE_URL` | — | **Yes** (checked at startup) |
| `CLERK_SECRET_KEY` | — | **Yes** (checked at startup) |
| `CONVEYOR_API_KEY` | `""` | Yes in production (empty → binds `127.0.0.1`) |
| `HARNESS_URL` | `http://127.0.0.1:3080` | Yes for analysis (the DSH harness) |
| `HARNESS_TOKEN` | — | Yes for analysis |
| `HARNESS_AUTOSTART` | `1` | Set to `0` on a server: start the harness yourself |
| `CLERK_JWKS_URL` | — | Yes for `/analyze/secure` |
| `VISHAP_DEV` | `false` | No — `true` downgrades the startup check to a warning |
| `PORT` | `5001` | No |
| `API_URL` | `http://localhost:5001` | No (UI) |

For a self-hosted model: `VISHAP_LLM_PROVIDER=custom`, `CUSTOM_BASE_URL`,
`CUSTOM_API_KEY` (any OpenAI-compatible server — vLLM, LM Studio, llama.cpp).

## Upgrading

```bash
cd /opt/conveyor_app
git pull --ff-only
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
systemctl restart vishap
```

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Service up, nothing on 5001 | `CONVEYOR_API_KEY` unset → bound to loopback |
| `Missing env vars: ...` in journal | `validate_config()` refused to start; fill `.env` |
| 401 on every GitHub webhook | `GITHUB_WEBHOOK_SECRET` wrong or missing |
| `password authentication failed` | `POSTGRES_PASSWORD` ≠ password in `DATABASE_URL` |
| API healthy, jobs stuck `queued` | worker not running, or `JOB_STORE` not `postgres` on the worker |
