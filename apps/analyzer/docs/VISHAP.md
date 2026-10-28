# Vishap

**Vishap** (Վիշապ) - Armenian dragon, guardian of treasures.

---

## Что значит имя

**Vishap** - в армянской мифологии дракон, хранитель сокровищ. Живёт в горах, охраняет воду и золото. Иногда - противник богов, иногда - их помощник.

**Почему Vishap для этого проекта:**

- **Хранитель** - Vishap охраняет код, ищет уязвимости, защищает от атак.
- **Многоликий** - Vishap анализирует code, config, spec, data, logs (5 типов материалов).
- **Древний** - армянская культура, аутентичность, личный бренд.
- **Запоминается** - `vishap analyze file.py` звучит.

**Раньше:** Vishap (конвейер) - техническое, безликое.
**Теперь:** Vishap - личное, культурное, узнаваемое.

---

## Использование

    vishap analyze file.py
    vishap analyze spec.md --output report.md
    vishap info
    vishap --version

---

## Символика

Vishap - не просто дракон. В армянской традиции:

- **Vishapak'ar** (Վիշապաքար) - «драконьи камни», мегалиты в горах Армении, изображающие рыб или драконов.
- **Vishap** связан с водой - источником жизни и знания.
- **Победа над Vishap** - сюжет в армянском эпосе (Ваагн, Трдат).

**Метафора для security-инструмента:**

Vishap охраняет код как дракон охраняет сокровище. Находит уязвимости, предотвращает атаки, документирует риски.

---

## Multi-material capability

| Материал | Пример | Что Vishap находит |
|----------|--------|---------------------|
| **code** | .py, .go, .js, .ts, .java, .rs | CWE, RCE, SQLi, OOB |
| **config** | .yaml, .json, .toml | secrets, misconfiguration |
| **spec** | .md (architecture) | design flaws, resilience |
| **logs** | .log, .txt (incidents) | root cause, blast radius |
| **data** | .json (audit trails) | PII, compliance |

**5 типов.** Не только код - полный анализ инженерных материалов.

---

## V5.8

**Возможности:**

- 6-stage pipeline (Orchestrator, Scanner, Analyst, Researcher, Synthesizer, Transmitter)
- Multi-material: code, config, spec, logs, data
- SAST/SCA: Bandit + Semgrep + pip-audit
- SARIF 2.1.0 output (GitHub Code Scanning)
- OWASP Top 10 mapping (28 CWE)
- Provenance tracking (source, git commit, branch)
- Exploitability (reachability, auth, blast radius)
- PII redaction before LLM (15 regex)
- API auth + rate limit + CORS
- Audit trail (SHA-256, 64-hex)
- Deterministic (same material -> same hash)

**Документация:**

- [PROOF.md](PROOF.md) - 13 доказательств
- [SECURITY.md](../SECURITY.md) - threat model
- [LIMITATIONS.md](LIMITATIONS.md) - honest boundaries
- [FAQ.md](FAQ.md) - 10 questions
- [COMPARISON.md](COMPARISON.md) - vs alternatives
- [COST.md](COST.md) - economics
- [ARCHITECTURE.md](ARCHITECTURE.md) - pipeline
- [ROADMAP.md](ROADMAP.md) - v6.0

---

## Философия

**Vishap - хранитель, не судья.**

Он находит риски, но не выносит приговор. Он документирует, но не решает. Он анализирует, но не заменяет эксперта.

**Vishap - усилитель, не замена.**

Он делает senior-инженера продуктивнее. Находит то, что человек может пропустить. Документирует то, что человек может забыть.

**Vishap - честен.**

Он признаёт границы (LIMITATIONS.md). Он не притворяется идеальным. Он показывает `VERIFY` там, где не уверен.

---

*Vishap V5.8 - production-ready. Армянский дракон-хранитель кода.*
