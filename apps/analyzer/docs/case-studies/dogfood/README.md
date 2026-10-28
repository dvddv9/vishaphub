# Dogfooding — Conveyor on Vishap

**Применение Conveyor к самому Vishap. Multi-material capability на себе.**

---

## Материалы (8)

| # | Файл | Тип | Level | task_type | PII | Compliance |
|---|------|-----|-------|-----------|-----|------------|
| 1 | `src/main.py` | code | D3 | review | False | EU AI Act |
| 2 | `src/pipeline/orchestrator.py` | code | D3 | review | False | HIPAA, PCI-DSS, GDPR, 152-ФЗ, EU AI Act |
| 3 | `src/pipeline/stages.py` | code | D3 | review | False | EU AI Act |
| 4 | `.github/workflows/tests.yml` | config | D2 | compliance | False | none |
| 5 | `pyproject.toml` | config | D2 | compliance | True | EU AI Act, GDPR, 152-ФЗ |
| 6 | `requirements.txt` | config | D2 | compliance | False | none |
| 7 | `README.md` | spec | D3 | other | False | HIPAA, PCI-DSS, GDPR, EU AI Act |
| 8 | `data/history.json` | data | D3 | incident | False | none |

---

## Ключевые находки

### Что Conveyor нашёл на себе

**Multi-material capability — доказана:**
- **Code** (`main.py`, `orchestrator.py`, `stages.py`) → D3, `task_type=review`
- **Config** (`ci-tests.yml`, `requirements.txt`, `pyproject.toml`) → D2, `task_type=compliance`
- **Spec** (`README.md`) → D3, `task_type=other`
- **Data** (`history.json`) → усечён (`truncated: true`, `original_size: 130939`)

**Калибровка `task_type` работает** — три разных типа материалов → три разных `task_type`: `review`, `compliance`, `other`.

**Compliance flags сработали:**
- `orchestrator.py` → HIPAA, PCI-DSS, GDPR, 152-ФЗ, EU AI Act (из-за ключевых слов в коде)
- `README.md` → HIPAA, PCI-DSS, GDPR, EU AI Act
- `pyproject.toml` → GDPR, 152-ФЗ, EU AI Act + `pii_detected: true`

---

## Структура

```
docs/case-studies/dogfood/
├── README.md           ← этот файл
├── code/
│   ├── main.md         ← src/main.py (API)
│   ├── orchestrator.md ← src/pipeline/orchestrator.py
│   └── stages.md       ← src/pipeline/stages.py
├── config/
│   ├── ci-tests.md     ← .github/workflows/tests.yml
│   ├── requirements.md ← requirements.txt
│   └── pyproject.md    ← pyproject.toml
├── spec/
│   └── readme.md       ← README.md
└── data/
    └── history.md      ← data/history.json
```

---

## Что это доказывает

1. **Multi-material capability** — работает на 4 типах материалов (code, config, spec, data).
2. **Калибровка `task_type`** — автоматически различает `review` / `compliance` / `other`.
3. **Audit trail** — каждый отчёт содержит `audit_id`, `material_hash` (64-hex), `session_id`.
4. **Truncation handling** — `orchestrator.py` (21578) и `history.json` (130939) усечены, но `material_hash_full` сохраняет оригинал.
5. **Dogfooding** — Conveyor проанализировал себя, не сломался, выдал валидные отчёты.

---

*Dogfooding. Vishap V5.8 на Vishap V5.8. См. PROOF.md для полной картины.*