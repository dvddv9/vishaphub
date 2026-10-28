# 🐉 Vishap Onboarding Guide

Welcome to Vishap! This guide will help you run the project locally and verify that everything works.

## 1. Prerequisites

- **Python:** 3.11 or 3.12
- **Node.js:** 18+ (for Next.js UI)
- **Git:** installed


## Download Links (Prerequisites)

Before running Vishap, install these tools. Download links are below.

### 1. Python 3.11+ (required)
- **Windows:** [python.org/downloads/windows](https://www.python.org/downloads/windows/)
- **macOS:** [python.org/downloads/macos](https://www.python.org/downloads/macos/)
- **Linux:** `sudo apt install python3.11` (Ubuntu) or `brew install python@3.11` (macOS)

### 2. Node.js 18+ (for Next.js UI)
- **All platforms:** [nodejs.org/en/download](https://nodejs.org/en/download/)
- **Recommended (nvm):** [github.com/nvm-sh/nvm](https://github.com/nvm-sh/nvm)

### 3. LLM provider (required for analysis)
- Every stage calls one OpenAI-compatible endpoint. Default: Claude. Get a key at
  [console.anthropic.com](https://console.anthropic.com/settings/keys).
- Then set `CUSTOM_LLM_URL=https://api.anthropic.com/v1`, `CUSTOM_LLM_MODEL=claude-sonnet-5-5`,
  `CUSTOM_LLM_KEY=<your key>` and `CUSTOM_LLM_SEND_TEMPERATURE=false`.
- Alternatives: DeepSeek, Groq, OpenAI, or a local model (Ollama, no key). See `.env.example`.

### 4. Postgres 16 (optional)
- **All platforms:** [postgresql.org/download](https://www.postgresql.org/download/)

### 5. Redis 7 (optional)
- **Windows (WSL2):** [learn.microsoft.com/windows/wsl](https://learn.microsoft.com/en-us/windows/wsl/install)
- **macOS:** `brew install redis`
- **Linux:** `sudo apt install redis-server`

### 7. Git
- **All platforms:** [git-scm.com/downloads](https://git-scm.com/downloads)

### 8. VS Code (recommended)
- **All platforms:** [code.visualstudio.com/download](https://code.visualstudio.com/download)

## Verify Installation

After installing, verify:

    python --version    # Python 3.11+
    node --version      # v18+

Then run:

    pip install vishap-analyzer==6.3.0
    vishap --version

## 2. Environment Setup (.env)

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

Required variables:
```env
# API
VISHAP_API_KEY=dev-key-123

# Postgres
DATABASE_URL=postgresql+asyncpg://vishap:vishap_dev@localhost:5432/vishap

# Redis (Celery)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Clerk (Auth) — get keys from https://dashboard.clerk.com
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...

# OTel (Observability)
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_SERVICE_NAME=vishap
OTEL_SDK_DISABLED=false
OTEL_METRICS_EXPORTER=none
```

## 3. Backend Startup

```bash
# 1. Clone
git clone https://github.com/dvddv9/vishap.git
cd vishap

# 2. Create venv
python -m venv .venv
source .venv/bin/activate  # Windows: .\\.venv\\Scripts\\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start databases (optional — Postgres + Redis; the API runs without them)
#    native installs, no containers: apt install postgresql redis-server
#    or set JOB_STORE=memory to skip them entirely

# 5. Run API
python -m src.main
```

**Verify:** `http://localhost:5001/docs` (Swagger UI) and `http://localhost:5001/health` (should return `{"status":"ok"}`).

## 4. UI Startup (Next.js)

```bash
cd ui-next
npm install
cp .env.local.example .env.local
# Fill in Clerk keys in .env.local
npm run dev
```

**Verify:** `http://localhost:3000` — Dashboard with Clerk sign-in.

## 5. Smoke Test (Verify Everything Works)

1. **API:** `curl http://localhost:5001/health` → `{"status":"ok"}`.
2. **UI:** Open `http://localhost:3000`, sign in via Clerk, upload a `.py` file, wait for the report.
3. **Metrics:** Open Grafana (`http://localhost:3001`), check `vishap_http_requests_total` graph.
4. **Traces:** Grafana → Explore → Tempo → query `{ resource.service.name = "vishap" }`.

## 6. Troubleshooting

| Error | Solution |
|---|---|
| `ModuleNotFoundError: No module named 'celery'` | `pip install -r requirements.txt` |
| `ConnectionError` / `LLM error` | The LLM endpoint is unreachable or the key is wrong: check `CUSTOM_LLM_URL`, `CUSTOM_LLM_MODEL` and `CUSTOM_LLM_KEY` (a Claude key starts with `sk-ant-`) |
| `Port 5001 already in use` | `netstat -ano | findstr :5001` → `taskkill /PID <PID> /F` |
| `401 Unauthorized` (UI) | Check Clerk keys in `.env.local` |
| `403 Forbidden` (GitHub App) | Check `GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET` |

## 7. Documentation & Links

- **Docs:** https://dvddv9.github.io/vishap/
- **Landing:** https://dvddv9.github.io/vishap/landing/
- **GitHub:** https://github.com/dvddv9/vishap
- **PyPI:** https://pypi.org/project/vishap-analyzer/

## 8. Project Structure

```
vishap/
├── src/                    # Python backend (FastAPI, Celery, pipeline)
├── ui-next/                # Next.js dashboard (React + Clerk)
├── src-tauri/              # Tauri desktop shell
├── docs-site/              # Docusaurus docs
├── deploy/                 # systemd unit + deployment notes
├── docs/                   # Internal docs (HANDOFF, ONBOARDING)
├── tests/                  # pytest suite
└── pyproject.toml          # Python package config
```

## 9. Support

- **Issues:** https://github.com/dvddv9/vishap/issues
- **Discussions:** https://github.com/dvddv9/vishap/discussions

Happy hacking! 🐉