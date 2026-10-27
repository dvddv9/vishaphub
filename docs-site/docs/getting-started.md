# Getting Started

Vishap is a 6-stage LLM pipeline that analyzes code, config, specs, logs, and data, and returns a structured Markdown report with risks, a STRIDE threat model, refactoring options, and an audit trail (SHA-256, PII detection, compliance flags, provenance).

## Prerequisites

- Python 3.11 or 3.12
- Node.js 18+ (for the UI)
- PostgreSQL 16 (for history and audit trail)
- An LLM provider (OpenAI-compatible endpoint set via `CUSTOM_LLM_*`):
  - **Claude** (default): api.anthropic.com
  - **Groq**, **DeepSeek**, **OpenAI**, **OpenRouter**
  - **Local model** (Ollama): no key needed

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

Scroll to the LLM Provider panel and choose Claude, Groq, DeepSeek, OpenAI, OpenRouter or a local model.

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
