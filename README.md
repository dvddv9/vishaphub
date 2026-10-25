<img width="1521" height="856" alt="Screenshot 2026-10-24 003530" src="https://github.com/user-attachments/assets/7bef0b59-3104-437b-8536-fdf5cc8fdd1b" />
# 🐉 Vishap

![Vishap Dashboard](docs/screenshots/dashboard.png)

[![PyPI](https://img.shields.io/pypi/v/vishap-analyzer.svg)](https://pypi.org/project/vishap-analyzer/)
[![CI](https://github.com/dvddv9/vishap/actions/workflows/ci.yml/badge.svg)](https://github.com/dvddv9/vishap/actions/workflows/ci.yml)
[![Docs](https://github.com/dvddv9/vishap/actions/workflows/docs.yml/badge.svg)](https://dvddv9.github.io/vishap/)
[![Version](https://img.shields.io/badge/version-7.3.16-blue)](https://github.com/dvddv9/vishap/releases/tag/v7.3.16)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

> 🐉 **Vishap** — 6-stage LLM pipeline for analyzing engineering materials (code, spec, logs, config, data).

**Vishap** takes a file as input → returns a structured Markdown report with risks, STRIDE threat model, refactoring options and **audit trail** with PII detection and compliance flags.

## 🌐 Live demo

| Service | URL | Stack |
|---------|-----|-------|
| **Frontend** | [vishap-ui.onrender.com](https://vishap-ui.onrender.com) | Next.js 16 · Node 24 |
| **Backend** | [vishap-zwpx.onrender.com](https://vishap-zwpx.onrender.com) | FastAPI · Docker |
| **API docs** | [/docs](https://vishap-zwpx.onrender.com/docs) | Swagger UI |

> ⚠️ Free tier: first request may take 30–50 s (cold start).

## 🎉 What's new in v7.3.17

- **Anthropic (Claude) provider** — `anthropic` в dropdown LLM Settings + auto-fill (`https://api.anthropic.com/v1/`, `claude-sonnet-4-20250514`). Ключ: `sk-ant-api03-...` из console.anthropic.com/settings/keys.
- **Android (Gemini) provider** — `android` в dropdown + auto-fill (`https://generativelanguage.googleapis.com/v1beta/openai/`, `gemini-2.0-flash`). Ключ: `AIza...` из aistudio.google.com/apikey.
- **Runtime config из `settings.json`** — `custom_client.py` читает `CUSTOM_LLM_*` из `settings.json` (runtime) поверх `.env` (defaults). Изменения в UI применяются «на лету».
- **Fix `NameError: _cfg`** — `_cfg` определена на уровне модуля (фикс `5ecbed3`).

- **reasoning_content fallback** — `custom_client.py` falls back to `message.reasoning_content` when `content` is empty (DeepSeek flash / V4).
- **Truncated JSON recovery** — `parse_json_response` recovers JSON truncated at `max_tokens` (closes unclosed `{` / `[`, cuts at last valid object).
- **Version sync** — single source of truth in `src/version.py`; CI checks `pyproject.toml` / `package.json` / `README.md`.

### Previous: v7.3.1

- **JavaScript / TypeScript support**: `detect_language` (.js/.jsx/.mjs/.cjs/.ts/.tsx), `js_parser.scan_js_patterns` (XSS, SQLi, RCE, path traversal, command injection), LLM hints in `build_prompt`.

### Audit evidence (#1–#8)
- **#1 `context_thread`** — wires metrics / cwe / evidence → activates #3 / #5 / #6
- **#2 `compute_critique_verdict`** — `NEEDS_VERIFICATION` / `REQUIRES_REVIEW` / `SAFE`; critical `risk_nodes` / `security` → `REQUIRES_REVIEW`
- **#3 `fidelity_index`** — 0.0–1.0; bias passed when in `[0.3, 0.95]`
- **#4 `negative_evidence`** — checked-but-not-found CWEs with reason
- **#5 `reproducer`** — runnable `python -c` + verified via `sys.executable`
- **#6 `bias_check`** — critical_ratio, FI-range, RCE-without-critical
- **#7 `CWE_MAPPING`** — 15 keys
- **#8 `report_date` / `valid_until`** — ISO + 90 days

### UI (`ui-next/`)
- **LLMSettings**: 7 providers (`custom` / `openai` / `groq` / `ollama` / `anthropic` / `android`)
- **Report v7.2 block**: Fidelity / Bias check / Reproducer / Negative evidence / Report date / valid_until
- **CORS fix**: `app.add_middleware(CORSMiddleware, ...)` — Settings form works in browser
- **mojibake fix**: em-dash `—`, ellipsis `…`, emoji 🐉

### Backend
- **`async_chat`** — respects `VISHAP_LLM_PROVIDER=custom`
- **Docker**: bind `0.0.0.0` — `-p 5001:5001` smoke-test passes
- **CI**: ruff F401 cleanup; `services.postgres` fix
- **Version sync**: 7.2.2 (`pyproject.toml`, `version.py`, `package.json`, `main.py`, `layout.tsx`)


## 🛠️ Features

- **6-stage pipeline:** Ingestion → Taint Analysis → Dataflow → Risk Assessment → Verdict → Report.
- **Multi-language:** Python, Java, C, **JavaScript / TypeScript** (AST + taint patterns).
- **Multi-provider LLM:** DeepSeek (custom), Anthropic (Claude), Android (Gemini), any OpenAI-compatible endpoint (Groq, OpenAI, Mistral, OpenRouter, Together).
- **Async API:** FastAPI + Celery workers (optional in-process fallback).
- **Security:** HMAC-SHA256 for API keys (with pepper), Fernet for secrets.
- **Observability:** Structlog (JSON), Prometheus `/metrics`, OpenTelemetry traces.
- **CI/CD:** GitHub Actions (tests, lint, docs deploy).
- **Desktop:** Tauri app for Windows.

## 🎯 When to use Vishap (and when not)

**Vishap is not a replacement for SonarQube or Snyk.** It is a **different tool** for **different material**.

| Tool | What it does | When to use |
|---|---|---|
| **SonarQube** | 40+ languages, Quality Gates, deterministic SAST, IDE integration | **Code review** — you have source code, you want fast, deterministic rules. |
| **Snyk** | Dependencies, containers, IaC, SBOM | **Supply chain** — you want CVE in deps / images / Terraform. |
| **Vishap** | 6-stage LLM pipeline, multi-material (code / spec / logs / config / data), audit trail with SHA-256, FI, runbook | **Spec / logs / config as material** — when you need an **audit trail** and **LLM reasoning**, not just rules. |

### Choose Vishap when

- You need to analyze **specs, logs, configs, or data** (not just code).
- You need an **audit trail** (SHA-256 provenance, `valid_until`, PII detection).
- You need a **runbook** (LLM-generated fix + verify) in the report.
- You want **FI (fidelity index)** — a measure of how honest the report is.
- You want **opt-in self-adversarial loops** (red team / translator / tester / fixer).

### Don't use Vishap when

- You just need **fast, deterministic SAST** on source code → **SonarQube**.
- You need **CVE in dependencies / containers / IaC** → **Snyk**.
- You need **IDE integration** (real-time linting) → **SonarLint** / **Snyk IDE**.

> **Bottom line:** Vishap **complements** SonarQube / Snyk. Run SonarQube for code, Snyk for deps, Vishap for **spec / logs / config + audit trail + runbook**.

## 📦 Quick Start

### Python (pip)

```bash
pip install vishap-analyzer==7.3.17
```

```python
from vishap_analyzer import analyze  # or: from src.pipeline.orchestrator import run_pipeline
result = analyze(material="def get_user(name): ...", filename="sqli.py")
print(result["audit"]["critique_verdict"])
```

> **Version pin:** `==7.3.15` — the version documented here. See [PyPI](https://pypi.org/project/vishap-analyzer/) for the latest.

### Backend (Docker)
```bash
docker build -t vishap .
docker run --rm -p 5001:5001 \
  -e VISHAP_DEV=true \
  -e VISHAP_LLM_PROVIDER=custom \
  -e CUSTOM_LLM_URL=https://api.deepseek.com/v1 \
  -e CUSTOM_LLM_MODEL=deepseek-chat \
  -e CUSTOM_LLM_KEY=sk-... \
  vishap
