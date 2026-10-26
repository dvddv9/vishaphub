<img width="1521" height="856" alt="Screenshot 2026-10-24 003530" src="https://github.com/user-attachments/assets/7bef0b59-3104-437b-8536-fdf5cc8fdd1b" />
# 🐉 Vishap

![Vishap Dashboard](docs/screenshots/dashboard.png)

[![PyPI](https://img.shields.io/pypi/v/vishap-analyzer.svg)](https://pypi.org/project/vishap-analyzer/)
[![CI](https://github.com/dvddv9/vishap/actions/workflows/ci.yml/badge.svg)](https://github.com/dvddv9/vishap/actions/workflows/ci.yml)
[![Docs](https://github.com/dvddv9/vishap/actions/workflows/docs.yml/badge.svg)](https://dvddv9.github.io/vishap/)
[![Version](https://img.shields.io/badge/version-7.4.4-blue)](https://github.com/dvddv9/vishap/releases)
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

## 🎉 What's new in v7.4.4

- **D0 fast path** — empty, trivial or unparseable material is classified D0 and skips the LLM.
- **`/analyze` is None-safe** — a stage that returns `None` no longer causes an HTTP 500.
- **Safer startup (v7.4.2)** — `/version` endpoint, fail-closed when `CONVEYOR_API_KEY` is not set, constant-time key comparison (`hmac.compare_digest`), `uuid4` session ids, default host `127.0.0.1` (override with `VISHAP_HOST`).
- **Claude plugin** — bundle renamed to `vishap-security-bundle`, tool annotations added, API key taken from plugin settings only.

### v7.4.0

**Logs as material** — LOG_PATTERNS (19): db_password, jwt_secret, aws_key, aws_secret, stripe_key, pii_email, pii_phone (E.164+`\b`), pii_passport_ru, credit_card, jwt_token, ssh_key, sqlmap, sqli_pattern, cmd_injection, imdsv1, cors_wildcard, csp_wildcard, cookie_insecure, xff_trust (CWE-348).

**scan_log + is_log_material** — deterministic log analysis; `detect_language('.log')` -> `'log'`.

**detect_exploitability(log)** — `reachable=True, blast=high` (log = incident by itself); `compute_reproducer(log)` -> `None + "log: use log analysis / DLP scan"`.

**Drift fixes** — `PII -> CWE-359` (`orchestrator.py:326`); `CWE-359 -> GDPR Art. 32` (`patterns.py:148`); `CWE-732` в `CWE_TO_OWASP` (S3 public-read -> Broken Access Control); `ASan -> sqlfluff + semgrep` в `RUNBOOKS["CWE-89"]`; `aws_key {16} -> {16,}`; `pii_phone -> \+\d[\d\-]{8,14}\d`; `patch-logs cleanup (4 -> 1)`.

**detect_language fix** — `ext` before `if` (UnboundLocalError).

**SECURITY.md v7.4.0** — SAST IMPLEMENTED (было NOT), `material_hash = sha256(material)` (было context+material), + Log Analysis, + Drift fixes, GDPR Art.32, L6.

**Version sync** — single source of truth in `src/version.py` (7.4.0); CI checks `pyproject.toml` / `package.json` / `README.md`.

Previous: [v7.3.17](#previous-v7317)

## 🛠️ Features

- **6-stage pipeline:** Ingestion → Taint Analysis → Dataflow → Risk Assessment → Verdict → Report.
- **Multi-language:** Python, Java, C, **JavaScript / TypeScript** (AST + taint patterns).
- **LLM backend:** any OpenAI-compatible endpoint via `CUSTOM_LLM_URL` / `CUSTOM_LLM_KEY` / `CUSTOM_LLM_MODEL` (DeepSeek by default; `.env.example` has OpenAI, Groq and Ollama examples).
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

## 🔌 Claude plugin

This repository is also a Claude plugin (`vishap-security-bundle`). It adds one read-only tool, `vishap_analyze`, that sends code, specs, logs or config text to the Claude API and returns a structured security report (CWE, STRIDE, fixes).

### Install

```text
/plugin marketplace add dvddv9/vishap
/plugin install vishap-security-bundle@vishap
```

The plugin server needs Python 3.10+ and its own dependencies: `pip install -r requirements-plugin.txt`.
When prompted, enter **Anthropic API Key** (and optionally the model, default `claude-sonnet-5-5`).

Ask Claude: *Use vishap-analyze to analyze: `db.execute(f"SELECT * FROM users WHERE name = '{name}'")`*

### Privacy

- **What leaves your machine:** the material you submit is sent to the Anthropic API (Claude) for analysis.
- **Whose key:** **your** Anthropic API key, entered in the plugin settings (`userConfig`) and passed to the server as `VISHAP_API_KEY`. The plugin does not read any credential from your environment and never uses the publisher's key. The key is stored in Claude Code config (sensitive), never in this repository.
- **What is stored:** no material is stored by the plugin itself. Responses are returned to Claude Code only.
- **Third parties:** Anthropic API (Claude). No other services.
- **Retention:** none on the plugin side; Anthropic API retention follows Anthropic policies (see https://www.anthropic.com/legal/privacy).
- **Background actions:** none. The plugin only runs when you call `vishap_analyze`.

## 📦 Quick Start

### Python (pip)

```bash
pip install vishap-analyzer
```

```python
from vishap_analyzer import analyze  # or: from src.pipeline.orchestrator import run_pipeline
result = analyze(material="def get_user(name): ...", filename="sqli.py")
print(result["audit"]["critique_verdict"])
```

> **Versions:** pin with `==X.Y.Z` for reproducible installs. See [PyPI](https://pypi.org/project/vishap-analyzer/) for available releases.

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
