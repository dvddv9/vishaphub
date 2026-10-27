# Roadmap — Vishap

**Where the project is going. What is deferred and why.**

---

## v7.0 — 2026-10 (current, shipped)

**Status:** production-ready slim release.

**Done:**
- Single UI surface: `ui-next/` (Streamlit removed).
- Single LLM chain: **DSH harness only** (`HARNESS_URL` / `HARNESS_TOKEN` / `HARNESS_COOKIE`).
- PyPI publish removed; Docker / compose / Docker Hub removed; deploy = `pip` + `systemd`.
- Desktop: Tauri app (Windows), auto-start backend from `.venv`, in-memory job store (no Postgres).
- `start_vishap_dev.bat`: one-click local dev (backend on `PORT=8080`, UI on `:3000`).
- AGPL-3.0-or-later everywhere (LICENSE, pyproject, README).
- 6-stage pipeline, SARIF 2.1.0, STRIDE, audit trail, PII redaction, provenance, runbook.
- Tests: **710 passed, 0 failed** (unit + API; e2e excluded).

---

## v7.1 — Q1 2027 (next)

**Focus:** cross-platform desktop + GitHub App polish.

### Desktop (Tauri)
- [ ] macOS build (`.dmg`, universal binary: Intel + Apple Silicon)
- [ ] Linux build (`.AppImage`, `.deb`)
- [ ] Auto-update (Tauri updater, signed artifacts)
- [ ] WebView2 detection + one-click install prompt (Windows)
- [ ] Native file picker / drag-and-drop into UI

### GitHub App
- [ ] PR diff auto-analysis (comment inline findings, SARIF upload to Code Scanning)
- [ ] Check-runs status (pass/fail quality gate)
- [ ] Installation flow (GitHub App manifest, `GITHUB_APP_ID` / `GITHUB_PRIVATE_KEY` / `GITHUB_WEBHOOK_SECRET`)
- [ ] Org-level config (`.vishap.yml` per repo)

### Harness
- [ ] `HARNESS_COOKIE` auto-refresh (GUI cookie expiry)
- [ ] Harness health badge (reachable / starting / off)
- [ ] Fallback: clear error message when harness is not running

---

## v7.2 — Q2 2027 (planned)

**Focus:** SaaS (optional, deferred from v7.0).

- [ ] Multi-tenant (Clerk orgs)
- [ ] Postgres job store (optional; memory still default for desktop)
- [ ] REST API v2 (async jobs, SSE streaming)
- [ ] Dashboard (metrics, trends, MTTR)
- [ ] Slack/Teams alerts

---

## v7.3 — Q3 2027 (planned)

**Focus:** integrations.

- [ ] GitLab CI integration (webhook + MR comments)
- [ ] VSCode extension (analyze current file / selection)
- [ ] CLI improvements (`vishap diff`, `vishap watch`)
- [ ] SBOM / SCA (CycloneDX, `pip-audit`, `govulncheck`)

---

## Later (2028+)

- [ ] Compliance certifications (SOC2, ISO 27001)
- [ ] Enterprise SSO (SAML, OIDC)
- [ ] On-prem air-gapped (no internet)
- [ ] Multi-language plugins (Kotlin, Swift, PHP)
- [ ] K8s operator (auto-scaling, HA)

---

## Explicitly deferred

- **Docker / compose / Docker Hub** — removed in v7.0 (slim). Local + `systemd` only.
- **PyPI publish** — removed in v7.0 (`vishap-analyzer` project deleted on PyPI).
- **Streamlit UI** — removed in v7.0 (single UI = `ui-next/`).
- **Direct DeepSeek/OpenAI/Ollama calls** — removed in v7.0 (harness is the only path).
