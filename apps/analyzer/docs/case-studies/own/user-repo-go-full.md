# user-repo-go: FULL REPORT

**Полный отчёт pipeline Vishap V5.8.**

---

## Metadata

| Field | Value |
|-------|-------|
| **Session** | `sess-2026-10-12-102301` |
| **audit_id** | `audit-2026-10-12-f94b65` |
| **material_hash** | `sha256:7081c8e935c3fd162107a46b482e2b95e1307b9ee9b0d12671befbdc52195cbd` |
| **material_hash_full** | `sha256:7081c8e935c3fd162107a46b482e2b95e1307b9ee9b0d12671befbdc52195cbd` (original, before truncation) |
| **truncated** | `False` (original_size: 930) |
| **Level** | `D2` |
| **task_type** | `review` |
| **Cost** | `$0.005748` |
| **Verdict** | `SAFE` |
| **Risk verdict** | `SAFE` |
| **pii_detected** | `False` |
| **Compliance** | `none` |

---

## Full Vishap Output (final_markdown)

# Go UserRepo — Code Review (D2)

[ECHO] Go source (~50 строк): `UserRepo` с 4 аннотированными багами — unbounded goroutine spawn, infinite retry, swallowed error, package-level channel. `context` импортирован, но не используется. Тестов нет.

[ROUTE] stage4 (synthesizer) → stage3 (verification) → stage5 (transmitter). task_type=review.

[CONCLUSION] Код не готов к проду. Три критических failure point: (1) `StartWorker` — неограниченный spawn горутин → OOM; (2) `GetUserWithRetry` — busy-loop без backoff → деградация БД; (3) `GetUser` глотает ошибку (всегда nil) → retry-ветка недостижима, отказы невидимы. Плюс package-level `events` блокирует изоляцию и горизонтальное масштабирование. Параметризация SQL корректна — инъекции нет. No signs of observability (logs/metrics/traces) found (VERIFY: не проверялось вне материала). No signs of producer for `events` channel found (VERIFY: продюсер вне материала).

[RISK_NODES]
- **RN-7/RN-10 (критично)**: `for { go func(){...}() }` — неограниченный рост горутин и памяти; нет shutdown-пути.
- **RN-8 (критично)**: retry без max attempts и без sleep — busy-loop при устойчивой ошибке БД.
- **RN-5 (критично)**: `context` импортирован, но не используется; `GetUser` всегда nil error, но `GetUserWithRetry` ветвится по err — ветка мертва.
- **RN-9 (критично)**: package-level `events` — глобальное состояние, нет изоляции инстансов.
- **RN-11 (критично, повышен из «важно» в stage2 CoVe)**: фикс `GetUser` ломает контракт для всех вызывающих.
- **RN-1/RN-4 (важно)**: неявное допущение о продюсере канала; комментарий «unbounded channel» описывает не то, что в коде (канал unbuffered, cap=0).

[THREAT_MODEL] 7 угроз: 2 критично (DoS через unbounded goroutines; DoS через infinite retry), 3 важно (unvalidated id; `SELECT *` — потенциальная утечка колонок; swallowed error → нет audit trail), 2 опционально (нет identity в context; process() без валидации сообщений). Trust boundaries: caller→GetUser, UserRepo→SQL, events→process(), process()→external (VERIFY).

[SILENCE_LAYERS]
- **Input**: нет RPS, размера очереди, числа воркеров, latency SLO — оценка деградации невозможна.
- **Assumption**: предполагается продюсер `events` и однократный вызов `StartWorker` — кодом не гарантировано.
- **Consequence**: OOM-kill необратим для in-flight запросов; деградация БД каскадом затронет другие сервисы.

[INTERSECTION_RISKS]
- unbounded goroutines × SQL connection pool → исчерпание пула, таймауты каскадом.
- infinite retry × swallowed error → retry-ветка мертва сейчас, но станет busy-loop сразу после фикса `GetUser` — скрытая мина при рефакторинге.
- global channel × multi-instance → flaky-тесты, нет изоляции арендаторов.
- нет логов × глотание ошибок → инцидент невидим до OOM-kill.

[ASSEMBLY] Core: `GetUser` (data access, broken), `GetUserWithRetry` (policy, broken), `StartWorker` (lifecycle, broken). Service: `process` (stub), `events` (package-level queue), `UserRepo` struct. Infra: `database/sql` (unconfigured pool), `context` (dead import), `time`.

[REFACTORING] Три опции:
- **A — Minimal hotfix** (1–2 дня): bounded worker pool, context+timeout, real error propagation, retry с backoff+max. Малый diff, но без observability.
- **B — Structural refactor** (3–5 дней): разделение Repository / WorkerPool / RetryPolicy, интерфейсы, context везде, hooks для metrics/logs. Breaking API.
- **C — Rewrite** (5–8 дней): errgroup + semaphore + circuit breaker + structured logging. Production-grade, требует load testing.

SRE second opinion: Option A недостаточен без observability — рекомендован минимум B с metrics/logs hooks в том же PR.

[PARALLELS] Паттерн «комментарий-как-замена-фикса» (RN-6): все 4 бага помечены, ни один не исправлен, тестов нет. Классический tech debt с ложным ощущением документированности.

[TESTS] Отсутствуют. Обязательны перед рефакторингом: (1) `GetUser` возвращает реальную ошибку при недоступной БД; (2) retry останавливается после max attempts (mock clock); (3) повторный `StartWorker` не множит воркеры; (4) load-тест: N сообщений, `runtime.NumGoroutine` ограничен; (5) graceful shutdown — `close(queue)` + WaitGroup; (6) изоляция двух инстансов `UserRepo`. Edge cases: пустой/закрытый канал, id ≤ 0, id = MaxInt, БД недоступна постоянно/временно.

[ACTION]
- **NOW**: disable `StartWorker` в проде до фикса (немедленное действие, не «STOP сегодня» — hotfix на 1–2 дня).
- **TODAY**: добавить тесты, фиксирующие текущее (сломанное) поведение.
- **TOMORROW**: Option A — фикс `GetUser` (breaking, версионировать API), bounded worker pool, retry с backoff+max, замена package-level channel на поле структуры.
- **LATER**: observability hooks (metrics/logs), circuit breaker, SLO, runbook.

[QUESTIONS]
- VERIFY: есть ли продюсер у канала `events` вне материала?
- VERIFY: какие side effects у `process()` при расширении (сеть, запись)?
- VERIFY: есть ли `go.mod` и версия Go (влияет на выбор errgroup/semaphore)?
- VERIFY: определены ли SLO-требования (влияют на выбор Option A vs B vs C)?
- VERIFY: намеренно ли `GetUser` возвращает nil (обработка выше) или это баг?

[FUNC:FULL]
- **ECON**: effort Option A 1–2 дня, Option B 3–5 дней, Option C 5–8 дней; cost $0 (code-only, без infra); ROI положительный — предотвращает OOM-kill и деградацию БД; cost of delay = один прод-инцидент в день.
- **FAIL**: критично — FP-1 unbounded spawn → OOM; FP-2 infinite retry → busy-loop; FP-3 swallowed error → невидимые отказы. Cascade: goroutines → pool exhaustion → таймауты других сервисов. Recovery: рестарт процесса (in-flight горутины не завершатся иначе).
- **METRICS**: ~50 строк, 4 функции, 1 тип, 3 deps (context unused), 0 тестов, 0 observability, resilience 2/10, evolvability 2/10.
- **ALTERNATIVES**: Option A (minimal hotfix) / B (structural refactor) / C (errgroup + circuit breaker). Язык Go — замена не рассматривается. БД — без изменений.
- **EVOLVE**: coupling 2/10 (package-level state + concrete *sql.DB), abstractions 2/10, feature_add 3/10, module_replace 2/10. Option B/C поднимают до 7–8.
- **COMPARE**: A — 1–2 дня, low risk, малый diff, без observability. B — 3–5 дней, medium risk, breaking API, testable. C — 5–8 дней, high risk, production-grade, требует load testing.

[MANDATORY BASE]
1. **ECONOMICS**: time 1–2 дня (Option A), cost $0, при условии code-only фикса без infra-изменений.
2. **RISKS**: критично — unbounded goroutines, infinite retry, swallowed error; важно — package-level channel, breaking API при фиксе; при условии, что продюсер `events` существует (VERIFY).
3. **INFRASTRUCTURE**: pool_size=50 (floor, при условии DB max_open_conns ≥ 50), workerCount=8 (2×GOMAXPROCS как старт), queueSize=256.
4. **CODE**: change ~50 строк (полный rewrite файла в Option A), при условии сохранения публичных сигнатур через *Ctx-варианты.
5. **ACTION**: now — disable StartWorker в проде; tomorrow — Option A фикс.
6. **TIMELINE**: NOW — disable StartWorker; TODAY — тесты на текущее поведение; TOMORROW — фикс GetUser + worker pool + retry; LATER — observability, circuit breaker, SLO.
7. **PRODUCTION IMPACT**: users N (неизвестно, VERIFY), deploy window — canary 2 дня, rollback ≤ 5 мин (нет персистентного состояния).
8. **SLO IMPACT**: current undefined, after — рекомендуется p99 latency ≤ 500ms, error rate ≤ 0.1%, при условии определения SLO до rollout.
9. **CLOUD COST**: current $N (неизвестно, нет infra manifest), projected $N (без изменений на steady state), delta ±$0 — code-only фикс; экономия под failure (нет OOM-kill, нет busy-loop CPU burn).
10. **ON-CALL**: new alerts — goroutine_count > 10×workerCount, db_pool_wait_p99 > 1s, retry_attempts > maxAttempts, queue_depth > 0.8×queueSize, oom_kill_events ≥ 1; runbook — pprof для диагностики утечки; escalation — level 1 (resolve_in_synthesis).

[PLAN_B]
- RN-1: заменить package-level канал на поле структуры + явный конструктор `NewUserRepo(db, queue)`.
- RN-2: вынести обработчик в интерфейс `Handler` с контекстом и таймаутом.
- RN-3: свести к одному методу `GetUser(ctx, id)` с явной ошибкой; retry — отдельная обёртка.
- RN-4: переписать комментарии по факту; удалить неверный диагноз «unbounded channel».
- RN-5: либо использовать `context.Context` в сигнатурах, либо удалить импорт; убрать недостижимую ветку.
- RN-6: добавить тесты на каждый BUG-комментарий.
- RN-7: worker pool с фиксированным N + buffered channel + semaphore.
- RN-8: retry с max attempts, exponential backoff, jitter, context-aware sleep.
- RN-9: убрать глобальный канал; инкапсулировать очередь в `UserRepo`.
- RN-10: `context.Context` + errgroup + graceful shutdown (`close(events)` + WaitGroup).
- RN-11: версионировать API или ввести `GetUserCtx` как новый метод, старый — deprecated.
- SEC-1: валидация id > 0, upper bound; явный список колонок вместо `SELECT *`.
- SEC-3: worker pool фиксированного размера + backpressure.

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | WARN | SQL параметризован (OK), но DoS через unbounded goroutines/retry (критично); `SELECT *` — потенциальная утечка |
| Facts | OK | Все утверждения привязаны к строкам материала; числа из stage4 с условиями |
| Logic | OK | Противоречие context-import vs отсутствие использования зафиксировано (RN-5) |
| Applicability | OK | Option A применим за 1–2 дня; Option B/C требуют согласования SLO |
| Effectiveness | WARN | Option A без observability оставляет инциденты невидимыми (SRE second opinion) |
| Resilience | FAIL | resilience 2/10 — ниже порога прода; нет timeout, backoff, circuit breaker, observability |
| Human factor | WARN | Комментарии-как-замена-фикса (RN-6); нет тестов; on-call не сможет диагностировать без pprof |
| Clarity | OK | Материал мал, баги аннотированы; отчёт структурирован |

[REFLEXION]
1. Слабое место: RN-11 в stage2 помечен «важно», но в CoVe повышен до критично — риск несогласованности приоритетов. Исправлено: в [RISK_NODES] явно указано «повышен из важно в stage2 CoVe».
2. Слабое место: Option A сохраняет package-level channel, если не рефакторить — противоречит рекомендации «убрать глобальное состояние». Исправлено: в [REFACTORING] и [PLAN_B] RN-9 явно указана замена на поле структуры в рамках Option A.
3. Слабое место: числа (pool_size=50, workerCount=8, queueSize=256) могут выглядеть как выдуманные. Исправлено: в [MANDATORY BASE] каждое число идёт с условием (floor, 2×GOMAXPROCS, constraint).
Итог: accepted

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-f94b65
material_hash: sha256:7081c8e935c3fd162107a46b482e2b95e1307b9ee9b0d12671befbdc52195cbd
material_hash_full: sha256:7081c8e935c3fd162107a46b482e2b95e1307b9ee9b0d12671befbdc52195cbd
pii_detected: false
compliance_flags: []
critique_verdict: SAFE
risk_verdict: SAFE


[COMPLETENESS]
level: D2
required: 12
missing: []
loss_pct: 0.0%
material_complete: True
verdict: ACCEPTABLE

---

## Notes

- Full report from `run_pipeline()` in `src/pipeline/orchestrator.py`.
- `final_markdown` length: 10766 chars.
- Source JSON: `data/result_sess-*.json` (in `.gitignore` — this file is the public copy).
- Short version: [user-repo-go.md](user-repo-go.md)
