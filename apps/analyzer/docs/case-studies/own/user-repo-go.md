# Case Study: User Repository (Go) — Goroutine Leak, Unbuffered Channel, Dead Retry

**Language:** Go
**Level:** D2
**Cost:** $0.005430
**Verdict:** SAFE
**Session:** sess-2026-10-10-153422
**Bugs planted:** 4 — Goroutine leak, Unbounded channel, No timeout, Infinite retry
**Bugs found:** 8
**False positives:** 0

**Key findings:** Goroutine-per-message leak, GetUser всегда err==nil (retry мёртв), retry без backoff, нет ctx/timeout, unbuffered channel. Conveyor исправил неточность: комментарий «unbounded channel» неверен — канал unbuffered (cap=0).


**Full report for client:** [user-repo-go-full.md](user-repo-go-full.md)

---

## Vishap Output

# Go UserRepo — Code Review (D2)

[ECHO] Go-файл ~50 строк: `UserRepo` (data access + worker lifecycle), package-level `events chan string`, `process(msg)`. 4 аннотированных бага (BUG 1–4). Тесты отсутствуют, `go.mod` отсутствует, `context` импортирован и не используется.

[ROUTE] stage0 → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). research_first=false, parallel_stages=false, subst_count=0.

[CONCLUSION] Код не готов к продакшену. Три критичных дефекта: (1) goroutine leak — `StartWorker` спавнит горутину на каждой итерации бесконечного цикла без отмены; (2) `GetUser` всегда возвращает `err == nil`, что делает retry-ветку `GetUserWithRetry` мёртвой и маскирует сбои БД; (3) retry без backoff/max attempts — при фиксе (2) превратится в busy-loop. Дополнительно: package-level mutable `events`, отсутствие ctx/timeout, observability, graceful shutdown, тестов. `resilience_score = 2/10`.

[RISK_NODES]
- **критично** — goroutine leak: `StartWorker` for-loop → `go func()` без выхода (risk node 7, 10).
- **критично** — `GetUser` err всегда nil → retry недостижим, сбои БД скрыты (risk node 1, 5).
- **критично** — retry без backoff/max/jitter → busy-loop после фикса (risk node 8).
- **критично** — нет ctx/timeout на SQL → зависший запрос держит соединение и горутину (SEC-2).
- **важно** — package-level `events` (unbuffered) → блокировка продюсеров, нет backpressure (risk node 11).
- **важно** — нет observability/SLO/runbook → утечка невидима до OOM-kill.
- **важно** — комментарий «BUG 1: unbounded channel» неточен: канал unbuffered (cap=0), не unbounded (risk node 4).

[ASSEMBLY] Слои: data access (`GetUser`) / orchestration (`StartWorker`) / retry policy (`GetUserWithRetry`) / side-effect (`process`). Связи: `StartWorker → events` (read, без ctx.Done), `StartWorker → process` (goroutine-per-message), `GetUserWithRetry → GetUser` (retry-ветка недостижима), `GetUser → sql.DB` (QueryRow без ctx), `external producer → events` (write, без контроля доступа). Critical path: `producer → events → goroutine → process(1s) → return`.

[REFACTORING] Рекомендуется вариант **B: Worker Pool + Handler interface** (вариант A отклонён — сохраняет goroutine-per-message и err всегда nil; вариант C — избыточен для текущего объёма). Шаги: (1) ctx в сигнатуры `GetUser`/`GetUserWithRetry` (breaking change); (2) err propagation в `GetUser`; (3) backoff + max attempts + jitter; (4) bounded worker pool вместо goroutine-per-message; (5) инкапсуляция `events` в структуру (breaking change для продюсеров); (6) graceful shutdown через `ctx.Done()`; (7) observability; (8) pool limits на `*sql.DB`.

[PARALLELS] Паттерн Repository присутствует номинально, но нарушен SRP (UserRepo смешивает data access и worker lifecycle). Worker pool номинален — фактически goroutine-per-message. Retry номинален — фактически недостижим. Аналогия: типичный «почти-правильный» Go-код, где каждый паттерн присутствует по имени, но не по семантике.

[TESTS] Отсутствуют (coverage 0%). Необходимо: unit `GetUser` с mock DB (err propagation), unit `GetUserWithRetry` (backoff, max attempts), concurrency `StartWorker` под нагрузкой (goroutine count), integration graceful shutdown, `go test -race`. Edge cases: пустой/отрицательный id, закрытие `events`, отмена ctx во время обработки, БД недоступна, медленный `process` при высоком RPS.

[ACTION] **NOW**: остановить деплой, если код в prod — рестарт при OOM. **TODAY**: фикс err propagation в `GetUser` + ctx/timeout на SQL (минимальный hotfix). **TOMORROW**: bounded worker pool + backoff/max/jitter + graceful shutdown. **LATER**: инкапсуляция `events`, observability, SLO, тесты, `go.mod`.

[QUESTIONS]
1. Идемпотентен ли `process(msg)`? Retry без идемпотентности дублирует побочные эффекты. (VERIFY)
2. Источник DSN и конфигурация `*sql.DB` (pool limits, timeouts)? Не показаны. (VERIFY)
3. RPS и размер очереди — для расчёта `pool_size` и `worker_pool_size`? (VERIFY)
4. Есть ли внешний брокер параллельно с `events`? (риск дублирования доставки)
5. Контролируемы ли продюсеры, пишущие в `events`?

[FUNC:FULL]
- **ECON**: effort ~2–3 дня (вариант B), cost $0 (inline-код, инфра не меняется), ROI высокий — предотвращает OOM-kill и потерю in-flight сообщений, cost of delay — необратимая потеря данных при инциденте.
- **FAIL**: критично — goroutine leak → OOM-kill; err всегда nil → сбои БД скрыты; retry без backoff → busy-loop. Cascade: leak → исчерпание pool БД → каскадный отказ. Recovery: только рестарт процесса, in-flight сообщения теряются.
- **METRICS**: ~50 строк, 4 функции + 1 метод, 3 deps (`context` unused, `database/sql`, `time`), 0 тестов, coverage 0%, нет `go.mod`, нет observability, resilience_score 2/10.
- **ALTERNATIVES**: A — minimal fix (отклонён: сохраняет leak и err всегда nil); B — worker pool + Handler interface (рекомендован); C — full redesign с Queue abstraction (избыточен). По БД: `database/sql` → `pgx`/`sqlx` при необходимости. По очереди: in-process channel → внешний брокер (Kafka/NATS) при росте.
- **EVOLVE**: coupling 2/10, abstractions 2/10, feature_add 3/10, module_replace 2/10, overall 2/10. Package-level mutable state и свободная `process` блокируют расширяемость; любое изменение ломает продюсеров.
- **COMPARE**: A — 0.5 дня, low risk, не решает критичные дефекты; B — 2–3 дня, medium risk (breaking change API), решает все критичные; C — 1–2 недели, high risk, избыточен для текущего объёма.

[MANDATORY BASE]
1. **ECONOMICS**: time ~2–3 дня (вариант B), cost $0 (inline-код, инфра не меняется), при условии отсутствия внешних продюсеров, требующих миграции.
2. **RISKS**: критично — goroutine leak, err всегда nil, retry без backoff; важно — package-level `events`, отсутствие observability; при условии нагрузки > 100 RPS деградация наступает за минуты.
3. **INFRASTRUCTURE**: pool_size=25 (SetMaxOpenConns), SetMaxIdleConns=10, SetConnMaxLifetime=5m, worker_pool_size=10, buffer=100, при условии RPS ≤ 100 и process ≤ 1s.
4. **CODE**: change ~50 строк → ~150 строк (вариант B), при условии сохранения публичного API продюсеров (иначе breaking change).
5. **ACTION**: now — остановить деплой; tomorrow — err propagation + ctx/timeout; later — worker pool + observability + тесты.
6. **TIMELINE**: NOW — hotfix err propagation; TODAY — ctx/timeout на SQL; TOMORROW — bounded worker pool + backoff; LATER — observability, SLO, тесты, `go.mod`.
7. **PRODUCTION IMPACT**: users N (неизвестно — input_silence), deploy window — maintenance, rollback — рестарт процесса (in-flight сообщения теряются, graceful shutdown отсутствует).
8. **SLO IMPACT**: current N/A (SLO не определены), after — рекомендуется availability 99.9%, p99 latency < 2s, queue depth < N, при условии внедрения observability.
9. **CLOUD COST**: current $0, projected $0, delta ±$0 — инфра не меняется (inline-код, analyze.py --mode cost не запускался).
10. **ON-CALL**: new alerts — goroutine_count > 1000, queue_depth > 10000, p99 > 2s, db_pool_wait > 100ms, error_rate > 1%; runbook — рестарт + диагностика pprof; escalation — level 2 (return_to_stage2, 2 критичных конфликта).

[REFLEXION]
1. Слабое место: `force_emergency: true` в stage4, но материал — учебный/ревью-контекст (stage0 gate_check: irreversible=нет). → Исправлено: emergency не активирован как INTERRUPTED, но критичность отражена в [RISK_NODES] и [ACTION] (остановить деплой).
2. Слабое место: числа `pool_size=25`, `worker_pool_size=10` без источника RPS. → Исправлено: каждое число в [MANDATORY BASE] идёт с условием («при условии RPS ≤ 100 и process ≤ 1s»); в [QUESTIONS] запрошен RPS.
3. Слабое место: `cloud_cost` = 0 без запуска analyze.py. → Исправлено: явно указано «analyze.py --mode cost не запускался», delta ±$0 обоснован отсутствием инфра-изменений.
Итог: accepted

---

*Audit trail добавляется pipeline'ом (orchestrator.py) — не генерируется трансмиттером.*

[AUDIT_TRAIL]
audit_id: audit-2026-10-10-87c88e
material_hash: sha256:5f1fe06c3dbc1265983e744397c247f941908a39e0cfe8f572edb0e673d6382b
pii_detected: false
compliance_flags: []
critique_verdict: SAFE


[COMPLETENESS]
level: D2
required: 12
missing: []
loss_pct: 0.0%
verdict: ACCEPTABLE

---

## Reproduce

    vishap analyze data/real_cases/own/user_repo.go
