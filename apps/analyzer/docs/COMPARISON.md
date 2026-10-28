# Comparison — Vishap vs Alternatives

**Честное сравнение с code-review и security-инструментами.**

---

## Матрица

| Tool | Что анализирует | Multi-material | Audit trail | Compliance | Cost (per analysis) | Self-hosted | LLM |
|------|-----------------|----------------|-------------|------------|---------------------|-------------|-----|
| **CodeRabbit** | Code (PR review) | Code only | No | No | Free + $24/user/mo | No | Yes (GPT-4) |
| **Qodo** | Code (test gen + review) | Code only | No | No | Free + $38/user/mo | No | Yes |
| **Graphite** | Code (PR stack) | Code only | No | No | Free + $40/user/mo | No | Yes (GPT-4) |
| **Snyk** | Deps + code (SAST) | Deps + code | Partial | PCI-DSS, GDPR flags | Free + $25/dev/mo | Partial (Enterprise) | No (deterministic) |
| **Semgrep** | Code (SAST rules) | Code only | No | Custom rules | Free + $40/user/mo | Yes (CE) | No (deterministic) |
| **Bandit / gosec** | Code (SAST) | Code only | No | No | Free | Yes | No |
| **Vishap** | Code, config, spec, data, logs | **5 types** | **Yes (SHA-256)** | HIPAA, PCI-DSS, GDPR, 152-FZ, EU AI Act | **$0 (local harness)** | **Yes (AGPL)** | Yes (DSH harness) |

---

## Где Vishap сильнее

### 1. Multi-material

CodeRabbit, Qodo, Graphite, Semgrep, Bandit - анализируют **только код**.

Vishap анализирует:
- **code** - .py, .go, .js, .ts, .java, .rs
- **config** - .yaml, .json, .toml
- **spec** - .md (architecture, requirements)
- **logs** - .txt, .log (incidents)
- **data** - .json (audit trails)

### 2. Deterministic audit trail

У конкурентов audit trail = нет или partial.

У Vishap:
- `material_hash` (SHA-256, 64 hex)
- `material_hash_full` (оригинал до усечения)
- `audit_id` (UTC timestamp)
- `session_id` (UTC)
- `pii_detected`, `compliance_flags`, `critique_verdict`, `risk_verdict`

**Каждый анализ воспроизводим.** Same material -> same hash.

### 3. Self-hosted + open source

- **CodeRabbit, Qodo, Graphite** - только SaaS.
- **Snyk, Semgrep** - SaaS + Enterprise self-hosted (платно).
- **Vishap** - self-hosted free (AGPL-3.0).

Приватный код **не уходит в облако** при self-hosted LLM (`VISHAP_LLM_PROVIDER=custom` + локальный OpenAI-совместимый сервер).

### 4. Стоимость

| Tool | 1000 анализов |
|------|---------------|
| CodeRabbit | $24 000/год (1 user) |
| Qodo | $38 000/год |
| Graphite | $40 000/год |
| Snyk | $25 000/год |
| Semgrep | $40 000/год |
| **Vishap** | **$7** (LLM only, self-hosted) |

**В 3400-5700 раз дешевле.**

### 5. Compliance flags

Vishap автоматически ставит:
- HIPAA (patient, diagnosis, medical record)
- PCI-DSS (payment, card, CVV)
- GDPR (personal data, right to erasure)
- 152-FZ (персональные данные)
- EU AI Act (LLM, foundation model)
- SECRETS (AWS, Stripe, GitHub tokens)

Snyk - partial (PCI-DSS, GDPR). Остальные - нет.

---

## Где Vishap проигрывает

### 1. CI integration

**CodeRabbit, Graphite** - готовые GitHub Apps, работают из коробки.

**Vishap** - нужен self-hosted deployment + webhook. См. `deploy/`.

### 2. SARIF output

**Semgrep, Bandit, gosec** - выдают SARIF -> GitHub Code Scanning.

**Vishap** - **не выдаёт SARIF** (пока). Только Markdown.

### 3. IDE integration

**Snyk, Semgrep, CodeRabbit** - VS Code, JetBrains plugins.

**Vishap** - только API + Streamlit UI.

### 4. Deterministic SAST

**Semgrep, Bandit, gosec, CodeQL** - детерминированные (regex + AST).

**Vishap** - LLM-based. Может ошибаться (false positives).

**Рекомендация:** Vishap + SAST = полное покрытие.

### 5. Dependency CVE scanning

**Snyk, Dependabot** - CVE база.

**Vishap** - не имеет CVE базы. Только анализ кода.

**Рекомендация:** Vishap + `pip-audit` / `npm audit` = полное покрытие.

### 6. Зрелость

| Tool | Возраст | Backing |
|------|---------|---------|
| CodeRabbit | 2023 | $60M funding |
| Qodo | 2022 | $50M+ |
| Graphite | 2020 | $52M |
| Snyk | 2015 | $1.2B valuation |
| Semgrep | 2017 | $104M |
| **Vishap** | **2026** | **Solo** |

**Vishap - новый проект.** Меньше кейсов, меньше community.

---

## Когда использовать Vishap

**Использовать Vishap когда:**
- Нужен **multi-material** анализ (не только code)
- Нужен **audit trail** для compliance
- Нужен **self-hosted** (приватный код)
- Нужна **низкая стоимость** ($0.007 vs $40+)
- Нужен **LLM-based** анализ (industry parallels, refactoring options)

**НЕ использовать Vishap когда:**
- Нужна **готовая CI-интеграция** (берите CodeRabbit/Graphite)
- Нужна **детерминированная SAST** (берите Semgrep/Bandit)
- Нужна **CVE база** (берите Snyk/Dependabot)
- Нужна **IDE integration** (берите Snyk/Semgrep)

**Идеальный стек:** Vishap + Semgrep + Snyk + тесты + code review.

---

*Last updated: 2026-10-12 | Vishap V5.8*