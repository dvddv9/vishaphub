# Security Policy — Vishap v7.4.0

Vishap is a security-analysis tool. Its own security is documented here.

**Last updated:** 2026-10-26 | **Vishap v7.4.0**

## Threat Model

### What we protect

| Asset | Boundary | Threat |
|-------|----------|--------|
| Material (code, spec, logs) | User -> API -> LLM | May contain PII, secrets, prompt injection |
| API (:5001) | External -> FastAPI | Unauthenticated access, DoS |
| LLM (local DSH harness) | Vishap -> DSH (127.0.0.1:3080) | Model may leak material outside the machine |
| API key (HARNESS_TOKEN) | .env -> process | Leak via git, logs |
| Audit trail (data/*.json) | Pipeline -> disk | Hash collisions, PII in logs |

### Trust boundaries

- **TB-1:** User -> API (:5001) — protected by X-API-Key
- **TB-2:** API -> LLM (local DSH harness) — protected by PII redaction
- **TB-3:** Material -> Pipeline — partial (SUBST_MAX_ATTEMPTS=2)
- **TB-4:** Pipeline -> disk — SHA-256 audit trail (64-hex)
- **TB-5:** Material -> Local FS — --context-root capped at 10 files / 10 KB

## What is implemented

### 1. PII/secrets redaction BEFORE LLM
**Location:** `src/tools/redact.py` — 15 regex patterns replace PII/secrets with placeholders before sending to LLM.

`redact_pii()` returns `(text, map)` — audit trail keeps `redaction_applied` + `redaction_map` for compliance.

### 2. API authentication
**Location:** `src/api/auth.py` — if `VISHAP_API_KEY` set -> `X-API-Key` header required. If empty -> API binds to 127.0.0.1 only.

### 3. API rate limiting
**Location:** `src/api/rate_limit.py` — `/analyze`: 10 req/min per IP; `/history`, `/mode`: 30 req/min per IP.

### 4. CORS restriction
**Location:** `src/main.py` — CORS allows only `localhost:8501` / `127.0.0.1:8501`.

### 5. LLM timeout + retry
**Location:** `src/llm/harness_client.py` — HTTP timeout: 30s per call; reply polling up to 600s. Auth: `HARNESS_TOKEN`. Failure mode: clear `[LLM error]` result, not exception.

### 6. EMERGENCY-downgrade protection
**Location:** `src/pipeline/orchestrator.py` — `EMERGENCY_INTERRUPT` is NOT downgraded if: Secrets/PII found, OR `CRITICAL_RISK_PATTERNS` match (RCE, SQLi, path traversal, XXE, SSTI, LDAPi).

### 7. Deterministic audit trail (v7.4.0)
- `material_hash = SHA-256(material)` — **без context** (стабилен: same material -> same hash)
- `material_hash_full = SHA-256(material)` — в v7.4.0 `context` **игнорируется** в `compute_hash()` (см. `src/pipeline/orchestrator.py:161`). Это **фикс** дрейфа: раньше `session_id` менял хеш.
- `compute_hash(material)` — только `material`, никаких `session_id` / `filename` / `timestamp`.

### 8. Secret storage
- `.env` in `.gitignore`
- `.env.example` for docs
- API key never logged

## Log Analysis (v7.4.0)

**Location:** `src/tools/sast.py`

- `LOG_PATTERNS` (19): `db_password`, `jwt_secret`, `aws_key`, `aws_secret`, `stripe_key`, `pii_email`, `pii_phone` (E.164+`\b`), `pii_passport_ru`, `credit_card`, `jwt_token`, `ssh_key`, `sqlmap`, `sqli_pattern`, `cmd_injection`, `imdsv1`, `cors_wildcard`, `csp_wildcard`, `cookie_insecure`, `xff_trust` (CWE-348)
- `scan_log(material)` -> findings
- `is_log_material(material)` -> True, если начинается с timestamp (`2026-`, `2025-`, `2024-`)
- `detect_exploitability(log)` -> `reachable=True, blast=high` (log = incident by itself)
- `compute_reproducer(log)` -> `None + "log: use log analysis / DLP scan"`
- `detect_language('.log')` -> `'log'`

## Drift fixes (v7.4.0)

- `PII -> CWE-359` (`orchestrator.py:326`): если `pii_detected`, `CWE-359` обязателен
- `CWE-359 -> GDPR Art. 32` (`patterns.py:148`): следствие
- `patch-logs cleanup`: 4 -> 1 блок (3 были в чужих функциях -> NameError)
- `aws_key {16}` -> `{16,}` (AKIA...EXAMPLE = 17)
- `pii_phone` -> `\+\d[\d\-]{8,14}\d` (E.164, без дат/портов)
- `CWE-732` в `CWE_TO_OWASP` (S3 public-read -> Broken Access Control)
- `ASan` -> `sqlfluff + semgrep` в `RUNBOOKS["CWE-89"]`
- `detect_language('.log')` — фикс `UnboundLocalError` (ext до if)

## SAST integration — IMPLEMENTED (v7.4.0)

**Location:** `src/tools/sast.py`

- `run_bandit(file_path)` — Bandit for Python
- `run_semgrep(file_path)` — Semgrep for multi-language
- `run_sast(file_path, language)` — unified
- `LOG_PATTERNS` (19) — deterministic log analysis
- `scan_log(material)` — scan logs
- `is_log_material(material)` — heuristic

## What is NOT implemented (honest boundaries)

1. **Material sandbox** — NOT implemented. Vishap does not execute material. Material is redacted, then sent only to a local DSH harness (127.0.0.1 by default) — there is no third-party LLM API call. Point `HARNESS_URL` at another host only if you trust that host; that is the one place where material can leave the machine.
2. **Prompt injection detection** — PARTIAL. `SUBST_MAX_ATTEMPTS=2` threshold. No semantic detection.
3. **Pre-commit hook for secrets** — NOT implemented. Redaction at analysis time, not commit time. Use gitleaks/TruffleHog separately.
4. **Dependency CVE scanning** — NOT implemented. `requirements.txt` uses `>=` without pinning. Use `pip-audit` separately.

## Known Limitations (formal)

- **L1:** `redact_pii` is regex-based; novel PII formats may bypass. Mitigation: `LOG_PATTERNS` (19) + custom regex via `.env`.
- **L2:** the harness model may rephrase PII despite redaction; audit trail records `redaction_applied`. Material never leaves the machine unless that harness is configured to use a remote model.
- **L3:** `data/audit_*.json` contains `redaction_map` (re-identification risk). Mitigation: `data/` gitignored; restrict FS access.
- **L4:** No SBOM signature; supply chain trust depends on PyPI.
- **L5:** `--context-root` reads arbitrary files under root; user must restrict scope.
- **L6 (v7.4.0):** `LOG_PATTERNS` is regex-based; may produce false positives on synthetic logs (e.g., `pii_phone` on dates). Mitigation: refined regex (`\+\d[\d\-]{8,14}\d`), `is_log_material()` gate.

## Responsible disclosure

**Do NOT open a public issue.** Email: `dvddv9@users.noreply.github.com`. Include description, steps, impact. We respond within 7 days.

## Supported versions

| Version | Supported |
|---------|-----------|
| 7.4.x | YES |
| < 7.4 | NO (upgrade) |

## Security checklist for deployment

- [ ] `VISHAP_API_KEY` set (not empty)
- [ ] `.env` NOT in git
- [ ] `HARNESS_TOKEN` rotated if leaked
- [ ] CORS restricted to your UI origin
- [ ] Reverse proxy terminates TLS
- [ ] `data/` backed up + access-controlled
- [ ] Rate limit appropriate for traffic