# Security Policy — Vishap v7.4.0

Vishap is a security-analysis tool. Its own security is documented here.

**Last updated:** 2026-10-26 | **Vishap v7.4.0**

## Threat Model

### What we protect

| Asset | Boundary | Threat |
|-------|----------|--------|
| Material (code, spec, logs) | User -> API -> LLM | May contain PII, secrets, prompt injection |
| API (:5001) | External -> FastAPI | Unauthenticated access, DoS |
| LLM provider (Claude by default; any OpenAI-compatible endpoint) | Vishap -> `CUSTOM_LLM_URL` | Material is sent to the provider; it leaves the machine unless the endpoint is local (Ollama, DSH) |
| API key (`CUSTOM_LLM_KEY`) | .env -> process | Leak via git, logs |
| Audit trail (data/*.json) | Pipeline -> disk | Hash collisions, PII in logs |

### Trust boundaries

- **TB-1:** User -> API (:5001) — protected by X-API-Key
- **TB-2:** API -> LLM provider (`CUSTOM_LLM_URL`) — protected by PII redaction
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
**Location:** `src/llm/client.py`, `src/llm/custom_client.py` — HTTP timeout `CUSTOM_LLM_TIMEOUT` (120s default). Auth: `CUSTOM_LLM_KEY` or the caller's `X-LLM-Api-Key`. Failure mode: clear `[LLM error]` result, not exception.

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

1. **Material sandbox** — NOT implemented. Vishap does not execute material. Material is redacted, then sent to the configured LLM endpoint (`CUSTOM_LLM_URL`; Claude at api.anthropic.com by default, or a provider the caller picks from the server allow-list). Material stays on the machine only with a local endpoint such as Ollama. Point `CUSTOM_LLM_URL` at a host only if you trust it.
2. **Prompt injection detection** — PARTIAL. `SUBST_MAX_ATTEMPTS=2` threshold. No semantic detection.
3. **Pre-commit hook for secrets** — NOT implemented. Redaction at analysis time, not commit time. Use gitleaks/TruffleHog separately.
4. **Dependency CVE scanning** — NOT implemented. `requirements.txt` uses `>=` without pinning. Use `pip-audit` separately.

## Known Limitations (formal)

- **L1:** `redact_pii` is regex-based; novel PII formats may bypass. Mitigation: `LOG_PATTERNS` (19) + custom regex via `.env`.
- **L2:** the model may rephrase PII despite redaction; audit trail records `redaction_applied`. Redacted material is sent to the configured LLM provider; it stays on the machine only with a local endpoint.
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
- [ ] `CUSTOM_LLM_KEY` rotated if leaked
- [ ] CORS restricted to your UI origin
- [ ] Reverse proxy terminates TLS
- [ ] `data/` backed up + access-controlled
- [ ] Rate limit appropriate for traffic
## Formal Threat Model (P2-10)

**Methodology:** ENISA / NIST SP 800-154 (data-centric threat modeling).

### 1. Scope

**In scope:**

- Vishap pipeline (6 stages: orchestrator -> scanner -> analyst -> researcher -> synthesizer -> transmitter).
- API (:5001), Next.js UI (`ui-next/`, desktop shell in `src-tauri/`), CLI (`vishap analyze`).
- Material: code, config, spec, logs, data (.py, .go, .js, .ts, .java, .rs, .txt, .md, .json).
- LLM: the endpoint set by the operator (`CUSTOM_LLM_URL` / `CUSTOM_LLM_KEY` / `CUSTOM_LLM_MODEL`; Claude by default), or a provider from the allow-list when the caller brings a key. Redacted material is sent to that provider; it stays on the machine only with a local endpoint (Ollama, DSH).
- Storage: `data/*.json` (history, audit, result).

**Out of scope:**

- Physical security (AWS / on-prem infra).
- Network layer (TLS termination, WAF, DDoS mitigation).
- Operating system / container runtime.
- The LLM provider's own model, prompts and network behaviour (separate service).

### 2. Assets

| Asset | Type | Impact if compromised | Owner |
|---|---|---|---|
| Material (source code, logs) | Data | IP leak, PII exposure | User |
| API key (`CUSTOM_LLM_KEY`) | Credential | Unauthorized LLM usage, cost | User |
| VISHAP_API_KEY | Credential | Unauthorized API access | User |
| Audit trail (data/*.json) | Data | Compliance violation, PII in logs | Vishap |
| Redaction map | Data | Re-identification | Vishap |
| Session history | Data | Privacy | User |

### 3. Trust boundaries

| ID | Boundary | Direction | Controls |
|---|---|---|---|
| TB-1 | User -> API | Inbound | X-API-Key, rate limit (10/min), CORS |
| TB-2 | API -> LLM provider | Outbound | PII redaction (15 regex) before send; provider chosen from a server allow-list, the base URL is never taken from a request |
| TB-3 | Material -> Pipeline | Inbound | SUBST_MAX_ATTEMPTS=2, CRITICAL_RISK_PATTERNS downgrade guard |
| TB-4 | Pipeline -> Disk | Outbound | SHA-256 audit trail (immutable), data/ gitignored |
| TB-5 | Material -> Local FS | Read | --context-root capped at 10 files / 10 KB |

### 4. Abuse Cases & Controls (STRIDE)

| # | STRIDE | Abuse Case | Control | Test |
|---|---|---|---|---|
| AC-1 | Spoofing | Unauthenticated API call | X-API-Key required when VISHAP_API_KEY set; bind 127.0.0.1 if empty | manual / test_api.py |
| AC-2 | Tampering | Prompt injection via material | SUBST_MAX_ATTEMPTS=2; PII redaction BEFORE LLM | tests/test_pipeline_mock.py |
| AC-3 | Repudiation | Audit trail forged or modified | SHA-256 hash of material; audit_id; UTC timestamp | tests/test_tools.py |
| AC-4 | Information Disclosure | PII sent to LLM | 15 regex redact (email, phone, AWS, Lemon Squeezy, GitHub, ...) | tests/test_tools.py |
| AC-5 | Information Disclosure | Secrets in logs | redact_pii applied to audit trail | tests/test_tools.py |
| AC-6 | Denial of Service | Large material -> OOM | MAX_CHARS=12000 truncation; max_file_bytes=10000 | tests/test_deps.py |
| AC-7 | Denial of Service | Rate-limit bypass | 10 req/min per IP on /analyze | manual |
| AC-8 | Elevation of Privilege | CWE downgrade (EMERGENCY -> SAFE) | CRITICAL_RISK_PATTERNS guard | tests/test_pipeline_mock.py |
| AC-9 | Information Disclosure | Code exfiltration via --context-root | Cap: 10 files, 10 KB each; stdlib filtered | tests/test_deps.py |
| AC-10 | Tampering | Baseline bypass (false PASS) | Skip-path returns exit 3 (SKIPPED) with --gate | tests/test_diff.py |

### 5. Verification

Each control maps to a test in `tests/` or a manual procedure:

- **Automated:** see Test column in section 4. 176 tests passing (`python run_tests.py`).
- **Manual:** see `docs/PROOF.md` for CLI run examples.
- **Pre-commit:** `.pre-commit-config.yaml` (gitleaks, bandit, ruff).

### 6. Compliance Readiness

| Standard | Status | Notes |
|---|---|---|
| SOC 2 CC6.1 | Partial | Access control (API key), rate limit; full audit logging -> in progress |
| SOC 2 CC7.2 | Partial | Monitoring (logging); SIEM integration -> out of scope |
| ISO/IEC 27001 A.14.2.5 | Partial | Secure development (pre-commit, tests); formal SDLC -> out of scope |
| PCI-DSS 3.2.1 | N/A | Vishap is a tool, not a card processor. CWE-89 controls documented. |
| GDPR Art. 32 | Yes | PII redaction, data minimization, audit trail |
| HIPAA 164.312 | N/A | Vishap is a tool, not a covered entity. No PHI processed by Vishap itself. |

### 7. Known Limitations (formal)

- **L1:** `redact_pii` is regex-based; novel PII formats may bypass. Mitigation: allow custom regex via `.env`.
- **L2:** the model may rephrase PII despite redaction; audit trail records `redaction_applied`. Redacted material is sent to the configured LLM provider; it stays on the machine only with a local endpoint.
- **L3:** `data/audit_*.json` contains `redaction_map` (re-identification risk). Mitigation: `data/` gitignored; restrict FS access.
- **L4:** No SBOM signature; supply chain trust depends on PyPI.
- **L5:** `--context-root` reads arbitrary files under root; user must restrict scope.

