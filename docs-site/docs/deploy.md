# Deploying Vishap

Vishap ships as a Python package (`pip install vishap-analyzer`) and runs as a
plain process under `systemd`. The repository also ships a `Dockerfile` and
`docker-compose.yml` (the hosted demo on Render is built from the Dockerfile; the
`docker-build` workflow only checks that the image builds and publishes nothing). The
VPS install below does not use them.

The VPS-specific checklist (TLS, systemd unit, backups) lives in
[`docs/VPS-DEPLOY.md`](https://github.com/dvddv9/vishap/blob/main/docs/VPS-DEPLOY.md).

> **Automated deployment is not wired up.** CI publishes the Python package on a
> `v*` tag (`publish.yml`). The steps below are manual.

## Quick start (local, no containers)

```bash
git clone https://github.com/dvddv9/vishap.git
cd vishap
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
# fill in DATABASE_URL, CONVEYOR_API_KEY, CLERK_SECRET_KEY
.venv/bin/alembic upgrade head
.venv/bin/python -m src.main
```

The API answers on `http://localhost:5001/health`; interactive docs are at
`/docs`.

Postgres and Redis are only needed for the multi-tenant paths and the
async job store. `JOB_STORE=memory` runs the API without either.

## Environment variables

The API validates a subset of the environment at startup and **refuses to
start** if a required value is missing:

| Variable | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | yes | Postgres connection string (`postgresql+asyncpg://...`) |
| `CLERK_SECRET_KEY` | yes | Authentication |
| `CONVEYOR_API_KEY` | in production | API-key auth; also makes the server bind `0.0.0.0` |
| `CLERK_JWKS_URL` | for `/analyze/secure` | Token verification keys |
| `FERNET_KEY` | yes for secrets | Encrypts stored integration secrets |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no | Trace export; empty disables it |

`VISHAP_DEV=true` downgrades the startup check to a warning, which is how the
demo environment runs without Clerk keys.

### Why `CONVEYOR_API_KEY` matters in production

`python -m src.main` binds `127.0.0.1` when no API key is configured — a
deliberate safety default for laptops. Behind a reverse proxy on another host
that means connection refused while the process health check stays green. Set
the key.

## Migrations

```bash
alembic upgrade head          # apply
alembic downgrade -1          # roll back one revision
alembic current               # what is applied
```

Revisions `002_add_rls_jobs` and `003_force_rls` install row-level security on
`jobs`. `003` makes the policy apply to the table owner too, so every code path
must bind a tenant (the API does this in its request handlers).

## Reverse proxy

The service binds `127.0.0.1:5001` when `CONVEYOR_API_KEY` is set. Terminate TLS
in front:

```caddyfile
api.example.com {
    reverse_proxy 127.0.0.1:5001
}
```

Forward `Host` and keep request bodies unmodified — the GitHub webhook signature covers
the raw payload.

## Health and observability

| Endpoint | Meaning |
| --- | --- |
| `GET /health` | liveness |
| `GET /metrics` | Prometheus exposition |

Traces go out over OTLP to whatever collector `OTEL_EXPORTER_OTLP_ENDPOINT`
points at. Tracing is fail-open: if the collector is down, requests still
succeed.

## Upgrades

```bash
cd /opt/conveyor_app
git pull --ff-only
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
systemctl restart vishap
```

Rollback: `git checkout <previous-tag>`, reinstall, restart. Migrations are
additive, so prefer rolling forward over downgrading.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `Missing env vars: DATABASE_URL...` on start | `validate_config()` — fill `.env` or set `VISHAP_DEV=true` |
| Process healthy, unreachable outside | `CONVEYOR_API_KEY` unset → bound to loopback |
| GitHub webhook returns 401 | `GITHUB_WEBHOOK_SECRET` missing, or the body was modified by a proxy |
| Jobs stay `queued` | worker not running, or `JOB_STORE` differs between api and worker |
| `/analyze/secure` returns 401 "Clerk not configured" | `CLERK_JWKS_URL` empty |
