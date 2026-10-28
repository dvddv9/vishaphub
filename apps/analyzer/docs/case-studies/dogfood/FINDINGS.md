# Dogfood Findings — Conveyor on Vishap

**Результат применения Conveyor к самому Vishap. Найдены реальные уязвимости в собственном продукте.**

---

## Сводка находок

| # | Файл | Risk | Критичных | Важно | Что найдено |
|---|------|------|-----------|-------|-------------|
| 1 | `src/main.py` | **EMERGENCY** | 5 | — | Нет auth на API; rate limit; TLS; 0.0.0.0 bind; sync `run_batch` в `async` |
| 2 | `src/pipeline/orchestrator.py` | SAFE | 4 | — | I/O errors; гонки на `session_id`; обход EMERGENCY-downgrade; **PII в cloud LLM без redaction** |
| 3 | `src/pipeline/stages.py` | SAFE | 1 | 4 | **`llm_chat` без timeout/retry** → блокировка pipeline |
| 4 | `.github/workflows/tests.yml` | SAFE | 0 | 4 | Нет `permissions:`; pinning по тегу vs SHA; нет timeout; нет concurrency |
| 5 | `pyproject.toml` | SAFE | 2 | — | **PII в METADATA**; нет lockfile; нет SPDX-лицензии |
| 6 | `requirements.txt` | SAFE | 0 | 0 | Нет lockfile; нет хэшей; нет CVE-сканирования |
| 7 | `README.md` | SAFE | 4 | — | API без auth; PII в audit-файлах; нет circuit breaker; race в history.json |
| 8 | `data/history.json` | **EMERGENCY** | 2 | — | **Коллизии `material_hash`**; PII без изоляции |

---

## P0 — критичные баги (найдены dogfooding)

### 1. Коллизии `material_hash` (data/history.json)

**Найдено:** Разные материалы (разный `material_size`, разный `verdict`) имеют **идентичный sha256**.

**Влияние:** Ломает дедупликацию и верификацию целостности. Audit trail не работает.

**Фикс:** Составной ключ — `sha256(material) + ':' + filename + ':' + timestamp`.

### 2. PII в cloud LLM без redaction (orchestrator.py)

**Найдено:** PII/секреты уходят в DeepSeek **до** детекции. Детектируются **после**.

**Влияние:** Приватный код + секреты в облаке. GDPR/152-ФЗ нарушены.

**Фикс:** Pre-send redaction — маскировать email/phone/passport/API keys **до** отправки.

### 3. `llm_chat` без timeout/retry (stages.py)

**Найдено:** `run_stage` вызывает `llm_chat` без timeout/retry. При зависании DeepSeek — блокировка всего pipeline.

**Фикс:** `timeout=60, max_retries=3, backoff=exponential`.

### 4. API без аутентификации (main.py)

**Найдено:** `POST /analyze`, `POST /history/clear`, `POST /mode` — без auth. `0.0.0.0:5001`.

**Фикс:** API-ключ через `X-API-Key` header + rate limit.

### 5. Обход EMERGENCY-downgrade (orchestrator.py)

**Найдено:** Автоматическое понижение EMERGENCY на основе regex-эвристики — обход защиты.

**Фикс:** Явный allowlist причин для downgrade, а не regex.

---

## Ключевой результат

**Conveyor нашёл свои собственные уязвимости.**

| Что подруга предполагала | Что Conveyor нашёл |
|--------------------------|-------------------|
| `.env` в репо? | PII в `pyproject.toml` METADATA |
| CORS `*` в FastAPI? | **Нет auth на API** (критичнее) |
| Rate limit? | **Нет rate limiting** на платный LLM |
| CI — `GITHUB_TOKEN`? | **Нет `permissions:`** |
| `data/` — PII? | **PII + коллизии hash** |
| `run_tests.py` — покрытие? | **Тестов 0%** |

**+ Conveyor нашёл то, что никто не предполагал:**
- Хардкод Windows-пути — ломает Linux
- `llm_chat` без timeout — блокировка pipeline
- **Коллизии `material_hash`** — разные материалы → одинаковый sha256
- PII в LLM без redaction

---

## Что это доказывает

1. **Multi-material capability** — code, config, spec, data — 4 типа, 8 материалов.
2. **Dogfooding работает** — Conveyor нашёл свои P0-баги, которые не нашли вручную.
3. **Калибровка `task_type`** — review, compliance, other, incident.
4. **Honest boundaries** — VERIFY-пометки там, где не проверил.
5. **Audit trail** — 64-hex hash в каждом отчёте.

**Conveyor — инструмент, не симуляция. Dogfooding подтвердил.**

---

*См. отчёты в code/, config/, spec/, data/ — полные детали.*