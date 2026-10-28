# Dogfood: main

**Source:** `src/main.py`
**Type:** main
**Level:** D3 | **task_type:** review
**Cost:** $0.008707 | **Verdict:** REQUIRES_REVIEW | **Risk:** EMERGENCY
**Session:** `sess-2026-10-12-120552` | **audit_id:** `audit-2026-10-12-641a33`
**material_hash:** `sha256:587e2bf3d714d4baa7ab5f756f069da3466142def2204230be9a5bbaf9b8b61f`
**material_hash_full:** `sha256:587e2bf3d714d4baa7ab5f756f069da3466142def2204230be9a5bbaf9b8b61f` (truncated: False, original_size: 11317)
**pii_detected:** False | **Compliance:** EU AI Act

---

## Vishap Output

# Vishap V5.8 — Отчёт по ревью `src/main.py`

[ECHO] FastAPI-сервер Vishap V5.8 (~330 строк): HTTP-слой над 6-стадийным LLM-конвейером. Эндпоинты `/analyze`, `/analyze/batch`, `/history`, `/history/clear`, `/mode`, `/health`. Уровень D3, task_type=review, session `sess-2026-10-12-XXXXXX`.

[ROUTE] stage0 → stage1 → stage2 → stage4 → stage3. research_first=false, parallel_stages=false, subst_count=0.

[CONCLUSION] Сервис функционален в dev-режиме, но **не готов к прод-деплою**: 5 критичных находок в TB-1 (клиент→FastAPI) — нет аутентификации ни на одном эндпоинте, `POST /history/clear` и `POST /mode` доступны любому клиенту, нет rate limiting на платный LLM, нет TLS, `0.0.0.0` bind. Дополнительно: sync `run_batch` в `async def` блокирует event loop; хардкод Windows-пути `C:/AI/conveyor_app/data/` ломает cache-hit на Linux; `json.loads(result_file)` без try/except → 500 на повреждённом файле. Resilience score 3/10. Признаков наличия тестов, CI/CD, observability не найдено (VERIFY: вне материала).

[RISK_NODES]
- **RN-1 (критично)** — неявное допущение: `result_{session}.json` всегда валиден по хардкод-пути `C:/AI/conveyor_app/data/`.
- **RN-6 (критично)** — стратегическое избегание: нет auth/authz ни на одном эндпоинте, нет rate limiting.
- **RN-8 (критично)** — надёжность: `json.loads` без try/except; `load_history`/`save_history` без обработки I/O.
- **RN-10 (критично)** — конкурентность: нет `asyncio.Lock`/файловых блокировок на history/mode/result.
- **RN-11 (критично, повышен из stage2 COVE)** — ломающие изменения: `AnalyzeResponse.cached` не выставляется в fresh-ветке; хардкод пути (BC-3) меняет поведение API без изменения кода.
- **RN-2, RN-3, RN-4, RN-5, RN-7, RN-9 (важно)** — см. stage2.

[PLAN_B]
- RN-1: `DATA_DIR` в `src.config`; `json.loads` в try/except → fallback на fresh pipeline.
- RN-2: `Idempotency-Key` header для `/analyze/batch`; явная документация неидемпотентности `/history/clear` и `/mode`.
- RN-3: удалить неиспользуемый `import run_pipeline`.
- RN-4: пробросить `verbose` в `run_pipeline_async` ИЛИ удалить поле из `AnalyzeRequest` и docstring.
- RN-5: заменить `getattr(req, 'force', False)` на `req.force`.
- RN-6: API-key middleware (`Depends`) + slowapi на `/analyze` и `/analyze/batch`; admin-role на `/history/clear` и `/mode`.
- RN-7: `await asyncio.to_thread(run_batch, ...)`.
- RN-8: try/except на все файловые операции → 503 при I/O.
- RN-9: SQLite (WAL) / Redis с транзакциями; либо явно ограничить деплой одним воркером.
- RN-10: `asyncio.Lock` + atomic write (tmp + `os.replace`).
- RN-11: единая `build_response(cached_result, is_cached)`.

[THREAT_MODEL]
- **TB-1 (клиент→FastAPI)**: 5 critical — S (подмена session_id), T (prompt injection через material), R (нет audit log), I (PII в result_*.json), D (DoS + cost amplification), E (privilege escalation через `/mode`).
- **TB-2 (FastAPI→ФС)**: T (подмена history/mode/result без checksum).
- **TB-3 (FastAPI→DeepSeek)**: I (утечка кода во внешний LLM), D (outage без retry/CB).
- **TB-4 (FastAPI→config/env)** — VERIFY, приоритет важно (flagged в stage2 COVE).
- **TB-5 (uvicorn→OS bind 0.0.0.0)** — VERIFY, приоритет важно.
- Top-3: SEC-1/E (`/mode` без auth), SEC-2/R (`/history/clear` без auth), SEC-4/D (нет rate limit).

[SILENCE_LAYERS]
- **input_silence**: нет RPS, размера material, latency LLM, частоты cache-hit — capacity-план невозможен.
- **assumption_silence**: `result_{session}.json` всегда существует и валиден по хардкод-пути.
- **consequence_silence**: `save_history([])` необратимо стирает историю — нет backup, soft-delete, audit.

[INTERSECTION_RISKS]
- async HTTP × sync `run_batch` → блокировка event loop, `/health` висит.
- файловая история × нет locks → гонка read-modify-write, потеря записей.
- открытый `/mode` × глобальное состояние → privilege escalation без следа.
- idempotency-by-hash × Windows path → на Linux cache-hit молча не срабатывает → двойная стоимость LLM.
- DeepSeek outage × нет CB → каскадный отказ.

[ASSEMBLY] HTTP-слой (FastAPI routes) → Pydantic DTO → pipeline (`orchestrator`, `batch`, `cost`) → storage (`history`, `mode`) → config. Критический путь: `POST /analyze` → `find_done_by_hash` → `run_pipeline_async` → DeepSeek → `sum_stage_costs` → `AnalyzeResponse`. Циклов в графе зависимостей нет.

[REFACTORING] Три варианта (stage4):
- **A — Hardening in-place** (2–3 дня): auth middleware, rate limit, try/except на ФС, `asyncio.to_thread`, путь в config, удаление мёртвых импортов, `req.force` напрямую. Закрывает 5/5 critical.
- **B — A + миграция state в SQLite/Redis** (5–7 дней): устраняет CONC-1, RN-9, RN-10; готов к multi-worker.
- **C — B + resilience-слой** (10–14 дней): retry/backoff, circuit breaker, structured logging, Prometheus, SLO, runbook, contract-тесты.

[PARALLELS] Паттерн «тонкий контроллер + pipeline-слой» — корректный. Антипаттерны: смешение top-level и локальных импортов; дублирование агрегации токенов между cache-hit и fresh ветками; `getattr` на явном поле; sync-вызов в async-эндпоинте.

[TESTS] Тестов в материале нет (VERIFY: вне материала). Необходимо: unit (`compute_hash`, `find_done_by_hash`, `build_response`, Pydantic-границы), integration (cache-hit vs fresh, batch с частичными ошибками, race `/history/clear` || `/history`, `/mode` set/get), contract (`AnalyzeResponse` в обеих ветках), security (401 без ключа, rate limit, body size limit), chaos (LLM timeout, ФС read-only, повреждённый `result_*.json`). Coverage target: ≥70% HTTP-слой, 100% cache/idempotency.

[ACTION]
- **NOW**: закрыть `POST /history/clear` и `POST /mode` за API-key (hotfix, часы); добавить rate limit на `/analyze` и `/analyze/batch`.
- **TODAY**: `try/except` вокруг `json.loads(result_file)` → 503; `await asyncio.to_thread(run_batch, ...)`; `DATA_DIR` в config; удалить мёртвые импорты; `req.force` напрямую.
- **TOMORROW**: полный auth middleware на все эндпоинты; `asyncio.Lock` + atomic write на history/mode; TLS termination + bind `127.0.0.1` за reverse-proxy.
- **LATER**: миграция state в SQLite/Redis (вариант B); retry/backoff + circuit breaker на DeepSeek; structured logging + request-id; Prometheus-метрики; SLO; runbook.

[QUESTIONS]
1. Режим деплоя — single-worker или multi-worker? (VERIFY: определяет, обязателен ли вариант B)
2. Существуют ли `src.config`, `src.pipeline.*`, `src.storage.*` и корректны ли они? (VERIFY: вне материала)
3. Может ли реальный `material` содержать PII/секреты? (VERIFY: определяет приоритет redaction)
4. Есть ли lock-файл зависимостей и CVE-сканирование? (VERIFY: вне материала)
5. Ожидается ли `verbose=True` в контракте API, или поле можно удалить?

[FUNC:FULL]
- **ECON**: effort A=2–3 дня, B=5–7, C=10–14 (rate не задан — не выдумываю); cost of delay — каждый день без auth/rate-limit = открытый `/mode`/`/history/clear` + неограниченные LLM-вызовы; при утечке PII — необратимо. ROI не вычисляется без rate и стоимости инцидента.
- **FAIL**: критично — `/history/clear` без auth (необратимая потеря), `/mode` без auth (privilege escalation), `json.loads` без try/except (500), нет locks (гонки), хардкод Windows-пути (cache-hit не работает на Linux). Cascade: DeepSeek outage → event loop забит → `/health` недоступен. Recovery: git revert кода возможен; потерянная история и потраченные токены — нет.
- **METRICS**: ~330 строк, 14 зависимостей, 0 тестов, 0 метрик, 0 tracing, 0 SLO, 0 алертов, 0 runbook. Resilience 3/10. Evolvability overall 4/10 (feature_add 4, module_replace 5, coupling 4, abstractions 3).
- **ALTERNATIVES**: A — hardening in-place (минимальный diff, single-worker); B — A + SQLite/Redis (multi-worker, транзакции); C — B + resilience-слой (retry/CB/observability/SLO). Язык/фреймворк менять не требуется — FastAPI адекватен.
- **EVOLVE**: coupling medium (прямые импорты без DI); abstractions слабые (нет `build_response`, нет интерфейсов storage); growth ограничен файловым состоянием (replicas=1); friction — правки в двух ветках при добавлении поля в `AnalyzeResponse`.
- **COMPARE**: A — 2–3 дня, низкий риск, закрывает 5/5 critical, не масштабируется. B — 5–7 дней, средний риск (миграция), multi-worker. C — 10–14 дней, высокий объём, прод-готовность + observability.

[MANDATORY BASE]
1. **ECONOMICS**: time A=2–3 дня / B=5–7 / C=10–14, cost $Y не вычисляется (rate не задан), при условии наличия инженерных ресурсов; cost of delay — необратимая потеря истории + cost amplification LLM.
2. **RISKS**: критично — RN-1, RN-6, RN-8, RN-10, RN-11; важно — RN-2, RN-3, RN-4, RN-5, RN-7, RN-9; при условии прод-деплоя в текущем виде.
3. **INFRASTRUCTURE**: pool_size не задан в материале (не выдумываю); replicas=1, при условии файлового состояния без миграции; autoscaling не применим при replicas=1.
4. **CODE**: change ~7 точек в `src/main.py` (мёртвые импорты, `req.force`, путь, try/except, `to_thread`, `Depends`, `build_response`), при условии варианта A; +3 новых файла (`config.py`, `security.py`, `storage/atomic.py`).
5. **ACTION**: now — hotfix auth на `/history/clear` и `/mode` + rate limit; tomorrow — полный middleware + locks + TLS; later — миграция state + resilience-слой.
6. **TIMELINE**: NOW — hotfix auth/rate-limit; TODAY — try/except ФС, `to_thread`, config; TOMORROW — middleware, locks, TLS; LATER — SQLite/Redis, retry/CB, observability, SLO.
7. **PRODUCTION IMPACT**: users N не задан (не выдумываю); deploy window — не задан; rollback кода N min не задан; при условии git revert — код откатывается, история и токены — нет.
8. **SLO IMPACT**: current SLO не определён (defined=false); after — рекомендация availability 99.5%, p95 `/analyze` < N сек (зависит от LLM), error-rate < 1%, при условии внедрения observability.
9. **CLOUD COST**: current $N не задан, projected $N не задан, delta ±$0 — no infrastructure change (изменения — код и конфиг), при условии варианта A/B/C без смены облачной инфраструктуры.
10. **ON-CALL**: new alerts — error_rate_5xx > 1%/5мин, p95 `/analyze` > 60s, cost_usd_per_hour > baseline×3, history_write_failures > 0, unauthorized_requests > 0; runbook — LLM outage, ФС full, cache corruption, cost spike; escalation — level 2 (return_to_stage2).

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | FAIL | Нет auth/authz/rate-limit/TLS; `/history/clear` и `/mode` открыты; 5 critical в TB-1 |
| Facts | OK | Все находки привязаны к строкам/эндпоинтам материала; числа не выдуманы |
| Logic | OK | Цепочки риск→план B→тест согласованы; конфликты Analyst/Synthesizer разрешены |
| Applicability | WARN | Вариант A применим сразу; B/C требуют подтверждения режима деплоя (VERIFY) |
| Effectiveness | WARN | A закрывает 5/5 critical, но не устраняет файловые гонки и отсутствие CB |
| Resilience | FAIL | Resilience 3/10; нет retry/timeout/CB на внешний LLM; нет locks |
| Human factor | WARN | `verbose` игнорируется — тихий слом контракта; `getattr` маскирует ошибки типизации |
| Clarity | OK | Docstrings на ключевых эндпоинтах; FastAPI auto-docs; русскоязычные комментарии |

[REFLEXION]
1. Слабое место: `force_emergency: true` из stage4 vs варианты A/B/C на 2–14 дней — противоречие. Исправлено: в [ACTION] NOW выделен hotfix auth/rate-limit (часы), полный A — TODAY/TOMORROW; force_emergency оправдан немедленным закрытием `/history/clear` и `/mode`.
2. Слабое место: числа (pool_size, cost, users, SLO) отсутствуют в материале — риск ложной точности. Исправлено: в [MANDATORY BASE] каждое число идёт с «не задан в материале — не выдумываю» + условие.
3. Слабое место: RN-11 повышен до критично в stage2 COVE, но в stage2.risk_nodes остался «важно». Исправлено: в [RISK_NODES] явно указано «повышен из stage2 COVE» с обоснованием (BC-3 + рассинхрон `cached`).
Итог: accepted

[CHANGELOG]
| # | What changed | Reason |
|---|--------------|--------|
| 1 | RN-11 повышен с «важно» до «критично» | Risk High (BC-3 + рассинхрон `cached`) |
| 2 | TB-4 (FastAPI→config/env) и TB-5 (uvicorn→OS bind) добавлены в threat model | Risk Medium (flagged в stage2 COVE) |
| 3 | force_emergency: true с hotfix NOW вместо полного A | Risk High (необратимость `/history/clear`) |

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-641a33
material_hash: sha256:587e2bf3d714d4baa7ab5f756f069da3466142def2204230be9a5bbaf9b8b61f
material_hash_full: sha256:587e2bf3d714d4baa7ab5f756f069da3466142def2204230be9a5bbaf9b8b61f
pii_detected: false
compliance_flags: ['EU AI Act']
critique_verdict: REQUIRES_REVIEW
risk_verdict: EMERGENCY


[COMPLETENESS]
level: D3
required: 12
missing: []
loss_pct: 0.0%
material_complete: True
verdict: ACCEPTABLE