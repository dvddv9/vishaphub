# Security Policy — Vishap V5.8

**Vishap is a security-analysis tool. Its own security is documented here.**

---

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

- TB-1: User -> API (:5001) — protected by X-API-Key
- TB-2: API -> LLM (local DSH harness) — protected by PII redaction
- TB-3: Material -> Pipeline — partial (SUBST_MAX_ATTEMPTS=2)
- TB-4: Pipeline -> disk — 64-hex SHA-256 audit trail

---

## What is implemented

### 1. PII/secrets redaction BEFORE LLM

**Location:** `src/tools/redact.py`

15 regex patterns replace PII/secrets with placeholders before sending to LLM:

```
email           -> <EMAIL_REDACTED>
phone_ru        -> <PHONE_REDACTED>
passport_ru     -> <PASSPORT_REDACTED>
snils           -> <SNILS_REDACTED>
iban            -> <IBAN_REDACTED>
aws_access_key  -> <AWS_ACCESS_KEY_REDACTED>
stripe_live_key -> <STRIPE_LIVE_KEY_REDACTED>
github_token    -> <GITHUB_TOKEN_REDACTED>
```

Audit trail keeps redaction_applied + redaction_map for compliance.

### 2. API authentication

**Location:** `src/api/auth.py`

- If VISHAP_API_KEY set -> X-API-Key header required.
- If empty -> API binds to 127.0.0.1 only.

### 3. API rate limiting

**Location:** `src/api/rate_limit.py`

- /analyze: 10 req/min per IP
- /history, /mode: 30 req/min per IP

### 4. CORS restriction

**Location:** `src/main.py`

CORS allows only localhost:8501 / 127.0.0.1:8501.

### 5. LLM timeout + retry

**Location:** `src/llm/harness_client.py`

- HTTP timeout: 30s per call; reply polling up to 600s
- Auth: `HARNESS_TOKEN` (the token DSH prints at startup)
- Failure mode: a clear `[LLM error] DSH harness is unreachable` result, not an exception

### 6. EMERGENCY-downgrade protection

**Location:** `src/pipeline/orchestrator.py`

EMERGENCY_INTERRUPT is NOT downgraded if:
- Secrets/PII found, OR
- CRITICAL_RISK_PATTERNS match (RCE, SQLi, path traversal, XXE, SSTI, LDAPi)

### 7. Deterministic audit trail

- material_hash = SHA-256 of analyzed slice (64 hex)
- material_hash_full = SHA-256 of original (64 hex)
- material_hash = sha256(context + material), context = filename:session_id -> no collisions

### 8. Secret storage

- .env in .gitignore
- .env.example for docs
- API key never logged

---

## What is NOT implemented (honest boundaries)

### 1. Material sandbox - NOT implemented
Vishap does not execute material. Material is redacted, then sent only to a **local DSH harness** (`127.0.0.1` by default) — there is no third-party LLM API call. Point `HARNESS_URL` at another host only if you trust that host; that is the one place where material can leave the machine.

### 2. Prompt injection detection - PARTIAL
SUBST_MAX_ATTEMPTS=2 threshold. No semantic detection.

### 3. Pre-commit hook for secrets - NOT implemented
Redaction at analysis time, not commit time. Use gitleaks/TruffleHog separately.

### 4. SAST integration - NOT implemented
Vishap is LLM-based. For deterministic SAST, add Bandit/Semgrep in CI.

### 5. Dependency CVE scanning - NOT implemented
requirements.txt uses >= without pinning. Use pip-audit separately.

---

## Responsible disclosure

1. Do NOT open a public issue.
2. Email: dvddv9@users.noreply.github.com
3. Include description, steps, impact.
4. We respond within 7 days.

---

## Supported versions

| Version | Supported |
|---------|-----------|
| 5.7.x | YES |
| < 5.7 | NO (upgrade) |

---

## Security checklist for deployment

- [ ] VISHAP_API_KEY set (not empty)
- [ ] .env NOT in git
- [ ] HARNESS_TOKEN rotated if leaked
- [ ] CORS restricted to your UI origin
- [ ] Reverse proxy terminates TLS
- [ ] data/ backed up + access-controlled
- [ ] Rate limit appropriate for traffic

---

*Last updated: 2026-10-12 | Vishap V5.8*

---

## Formal Threat Model (P2-10)

**Methodology:** ENISA / NIST SP 800-154 (data-centric threat modeling).

### 1. Scope

**In scope:**

- Vishap pipeline (6 stages: orchestrator -> scanner -> analyst -> researcher -> synthesizer -> transmitter).
- API (:5001), Next.js UI (`ui-next/`, desktop shell in `src-tauri/`), CLI (`vishap analyze`).
- Material: code, config, spec, logs, data (.py, .go, .js, .ts, .java, .rs, .txt, .md, .json).
- LLM: a local DSH harness only (`HARNESS_URL`, `HARNESS_TOKEN`). Vishap performs no direct DeepSeek / OpenAI / third-party API call — material stays on the machine it runs on.
- Process start: when the harness is not answering and `HARNESS_AUTOSTART` is on (default), Vishap spawns `dsh web` detached from `HARNESS_CMD` (or the DSH install path). It never starts a harness for a non-loopback `HARNESS_URL`.
- Storage: `data/*.json` (history, audit, result).

**Out of scope:**

- Physical security (AWS / on-prem infra).
- Network layer (TLS termination, WAF, DDoS mitigation).
- Operating system / container runtime.
- DeepSeek Harness' own model, prompts and network behaviour (separate product).

### 2. Assets

| Asset | Type | Impact if compromised | Owner |
|---|---|---|---|
| Material (source code, logs) | Data | IP leak, PII exposure | User |
| API key (HARNESS_TOKEN) | Credential | Unauthorized harness usage | User |
| VISHAP_API_KEY | Credential | Unauthorized API access | User |
| Audit trail (data/*.json) | Data | Compliance violation, PII in logs | Vishap |
| Redaction map | Data | Re-identification | Vishap |
| Session history | Data | Privacy | User |

### 3. Trust boundaries

| ID | Boundary | Direction | Controls |
|---|---|---|---|
| TB-1 | User -> API | Inbound | X-API-Key, rate limit (10/min), CORS |
| TB-2 | API -> LLM (local DSH harness) | Outbound | PII redaction (15 regex) before send; loopback-only URL |
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
- **L2:** the harness model may rephrase PII despite redaction; audit trail records `redaction_applied`. Material never leaves the machine unless that harness is configured to use a remote model.
- **L3:** `data/audit_*.json` contains `redaction_map` (re-identification risk). Mitigation: `data/` gitignored; restrict FS access.
- **L4:** No SBOM signature; supply chain trust depends on PyPI.
- **L5:** `--context-root` reads arbitrary files under root; user must restrict scope.

