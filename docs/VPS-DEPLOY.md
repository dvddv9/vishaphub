# Deploying Vishap to a VPS

Step by step, from an empty account to a working API behind TLS. Roughly 30
minutes, most of it DNS propagation.

Vishap is distributed through **PyPI** (`pip install vishap-analyzer`) and runs as a
plain Python service under **systemd**. There is no container in the VPS
deployment path: the repository still ships a `Dockerfile` and `docker-compose.yml`
(the hosted demo on Render is built from the Dockerfile), but a VPS install is `apt` for the services, `pip` for the app, `systemd` for the
process.

> **Automated deployment is not wired up.** CI builds and publishes the Python
> package on a `v*` tag (`publish.yml`); the steps below are manual.

## 1. Create the server

Hetzner Cloud is the cheapest sane option: **CX22** (2 vCPU / 4 GB / 40 GB) is
around €5/month and comfortably runs the API, Postgres and Redis.

- Location: closest to your customers (EU for GDPR simplicity).
- Image: **Ubuntu 24.04**.
- SSH key: add yours — password login should stay disabled.
- Firewall: allow **22**, **80**, **443** only. Do not open 5001.

No swap tuning, no custom kernel.

## 2. Point DNS at it

At your registrar (or Cloudflare with proxying off until certificates work):

```
api.example.com.  A  <server-ipv4>
```

Wait for propagation:

```bash
dig +short api.example.com
```

## 3. Install the services

```bash
ssh root@<server-ip>
apt update && apt install -y python3-venv python3-pip git postgresql redis-server caddy
```

Postgres and Redis listen on `127.0.0.1` by default, which is what you want — only
the API is exposed, and only through the reverse proxy.

## 4. Create the database

```bash
sudo -u postgres psql -c "CREATE USER vishap WITH PASSWORD '<POSTGRES_PASSWORD>';"
sudo -u postgres psql -c "CREATE DATABASE vishap OWNER vishap;"
```

## 5. Install the application

```bash
adduser --system --group --home /opt/conveyor_app conveyor
git clone https://github.com/dvddv9/vishap.git /opt/conveyor_app
cd /opt/conveyor_app
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

`.venv/bin/pip install vishap-analyzer==<version>` also works if you do not want the
git checkout — but migrations and the systemd unit live in the repo, so the clone is
the simpler path.

## 6. Fill in `.env`

```bash
cd /opt/conveyor_app
nano .env
```

Minimum for a working deployment:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://vishap:<POSTGRES_PASSWORD>@127.0.0.1:5432/vishap` |
| `CONVEYOR_API_KEY` | long random string — **without it the API binds 127.0.0.1** |
| `HARNESS_URL` | `http://127.0.0.1:3080` — the DSH harness must run on the same box |
| `HARNESS_TOKEN` | token printed by DSH at startup |
| `HARNESS_AUTOSTART` | `0` on a server — run `dsh web` yourself under its own service |
| `CLERK_SECRET_KEY` | `sk_live_...` |
| `CLERK_JWKS_URL` | `https://<clerk-instance>/.well-known/jwks.json` |
| `FERNET_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

Add `VISHAP_TENANT_KEYS=true` only if you issue per-tenant API keys —
it turns on the `tenants` table lookup for `X-API-Key`.

Keep `JOB_STORE=postgres` (the default) if you run the worker; `JOB_STORE=memory`
is for a single-process API.

## 7. Apply migrations

```bash
cd /opt/conveyor_app
sudo -u conveyor .venv/bin/alembic upgrade head
```

## 8. Run it under systemd

```bash
cp deploy/systemd/vishap.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now vishap
systemctl status vishap --no-pager
curl -fsS http://127.0.0.1:5001/health
```

The unit expects `User=conveyor`, `WorkingDirectory=/opt/conveyor_app` and
`EnvironmentFile=/opt/conveyor_app/.env` — adjust if you used different paths.

For async jobs add a second unit with the same environment:

```ini
[Service]
User=conveyor
WorkingDirectory=/opt/conveyor_app
EnvironmentFile=/opt/conveyor_app/.env
ExecStart=/opt/conveyor_app/.venv/bin/celery -A src.api.celery_app worker --loglevel=info
Restart=on-failure
```

## 9. TLS

Caddy in front, two lines:

```
api.example.com {
    reverse_proxy 127.0.0.1:5001
}
```

```bash
cp /dev/stdin /etc/caddy/Caddyfile <<'EOF'
api.example.com {
    reverse_proxy 127.0.0.1:5001
}
EOF
systemctl reload caddy
```

Verify: `curl https://api.example.com/health`.

Do not rewrite request bodies — the GitHub webhook signature covers the raw payload.

## 10. Smoke test

```bash
curl -fsS https://api.example.com/health

# an analysis end to end
curl -sS -X POST https://api.example.com/analyze/async \
  -H "X-API-Key: $CONVEYOR_API_KEY" -H 'Content-Type: application/json' \
  -d '{"material": "print(1)", "filename": "t.py"}'
```

Then poll `/status/{job_id}` until `done` and fetch `/report/{job_id}`.

## Upgrading and rolling back

```bash
cd /opt/conveyor_app
git pull --ff-only
.venv/bin/pip install -r requirements.txt
sudo -u conveyor .venv/bin/alembic upgrade head
systemctl restart vishap
```

Rollback: `git checkout <previous-tag>` and repeat (migrations are additive; if a
release adds one, roll forward rather than down).

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `Missing env vars: ...` and the service exits | `validate_config()` refused to start |
| Health check green, `curl` from outside refused | `CONVEYOR_API_KEY` unset → bound to loopback |
| `relation "tenants" does not exist` | migrations not applied: `alembic upgrade head` |
| Every `/analyze` returns 401 | `CONVEYOR_API_KEY` mismatch, or `VISHAP_TENANT_KEYS=true` with no matching tenant row |
| Jobs stay `queued` | worker not running, or its `DATABASE_URL` differs from the API's |
| `permission denied` on `data/` | the unit runs as `conveyor`; `chown -R conveyor:conveyor /opt/conveyor_app/data` |

## Backups

Two things matter: the database and `/opt/conveyor_app/data` (reports and result
JSONs). A nightly `pg_dump` to object storage is the minimum; `data/` can be rebuilt
from job results if it is lost.
