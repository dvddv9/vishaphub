# Getting Started

Vishap is a 6-stage LLM pipeline that analyzes code, config, specs, logs, and data, and returns a structured Markdown report with risks, a STRIDE threat model, refactoring options, and an audit trail (SHA-256, PII detection, compliance flags, provenance).

## Prerequisites

- Python 3.11 or 3.12
- Node.js 18+ (for the UI)
- PostgreSQL 16 (for history and audit trail)
- One of the following LLM providers:
  - **Custom (OpenAI-compatible)**: Groq, OpenAI, Mistral, OpenRouter, Together
  - **Harness (DSH)**: local DeepSeek Harness
  - **DeepSeek (direct)**: direct API calls

## Install

```powershell
python -m venv venv
# Windows
.\venv\Scripts\Activate.ps1
# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
Copy .env.example to .env and fill in your keys. For local development without Stripe/Clerk, set VISHAP_DEV=true.

Quick start

CLI

```bash
vishap analyze path/to/file.py
```

API

```powershell
python -m src.main
# -> http://localhost:8080/docs

curl -X POST http://localhost:8080/analyze `
  -H "Content-Type: application/json" `
  -d '{\"material\": \"def f(): pass\", \"filename\": \"x.py\"}'
```

UI

```powershell
cd ui-next
npm install
npm run dev
# -> http://localhost:3000
```

Scroll to the LLM Provider panel and choose Custom, Harness, or DeepSeek.

Async (Celery + Redis)

```powershell
celery -A src.api.celery_app worker --loglevel=info

curl -X POST http://localhost:8080/analyze/async `
  -H "Content-Type: application/json" `
  -d '{\"material\": \"def f(): pass\", \"filename\": \"x.py\"}'
# -> {\"job_id\": \"...\", \"status\": \"queued\"}

curl http://localhost:8080/status/<job_id>
curl http://localhost:8080/report/<job_id>
```

Next steps

· Architecture
· API Reference
· CLI
· Case Studies

```
