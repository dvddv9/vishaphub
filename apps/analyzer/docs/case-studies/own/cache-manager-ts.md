# Case Study: Cache Manager (TypeScript) — Cache Stampede, No TTL, KEYS *

**Language:** TypeScript
**Level:** D2
**Cost:** $0.006055
**Verdict:** SAFE
**Session:** sess-2026-10-10-153858
**Bugs planted:** 4 — No TTL, Cache stampede, No error handling, KEYS *
**Bugs found:** 9
**False positives:** 0

**Key findings:** KEYS * блокирует Redis event loop + cross-tenant destruction, cache stampede (thundering herd), set() без TTL → OOM, нет try/catch. Refactoring: single-flight + distributed lock + negative caching + SCAN/UNLINK. Параллель: Facebook memcache lease.


**Full report for client:** [cache-manager-ts-full.md](cache-manager-ts-full.md)

---

## Vishap Output

# CacheManager — Code Review (D2)

[ECHO] TypeScript `CacheManager` (~35 строк, 4 метода) поверх `ioredis`. 4 аннотированных бага: нет TTL, cache stampede, нет error handling, `KEYS *`. Класс заявлен как cache-aside facade, но не управляет жизненным циклом кэша.

[ROUTE] stage4 (синтез) → stage3 (рекомендации). Research не запускался (`research_first=false`). Substitution не обнаружена.

[CONCLUSION] Кэш на горячем пути без TTL, без error handling, без lock и без namespace. В проде это даёт: рост памяти Redis до OOM, каскадные отказы при деградации Redis, перегрузку origin при stampede, риск удаления чужих ключей в shared DB. Resilience score 2/10. Рекомендуется Option B (hardened + namespaced + DI) — но требуется верификация deployment topology и метрик перед фиксацией lockTTL.

[RISK_NODES]
- **критично** — `invalidateAll()` через `KEYS *` блокирует Redis event loop (O(N)); на shared DB удаляет чужие ключи (сессии/очереди) необратимо.
- **критично** — `getOrLoad()` check-then-act race: N параллельных промахов → N вызовов loader → перегрузка origin (thundering herd).
- **критично** — `set()` без TTL → неограниченный рост памяти Redis → OOM → отказ всех потребителей.
- **критично** — нет try/catch ни в одном методе; Redis down = unhandled rejection вверх по стеку. `JSON.parse(null)` в `get()` бросает на нормальном cache miss.
- **важно** — нет namespace/prefix; `invalidateAll()` в shared Redis DB = cross-tenant data destruction.
- **важно** — `new Redis()` без TLS/AUTH; module-level singleton исполняется при импорте (нет DI, риск подключения к прод-Redis в тестах).
- **важно** — `any` типы + JSON без схемы; несериализуемые значения (Date/Map/circular) молча теряются или бросают.
- **важно** — нет observability (hit/miss, latency, keyspace size), нет SLO, нет алертов, нет runbook.

[ASSEMBLY] Иерархия: **core** — CacheManager, заявленная single-flight семантика (не реализована), TTL/eviction policy (отсутствует). **service** — ioredis singleton, loader callback, JSON serialization, namespace (отсутствует). **infra** — Redis server (shared keyspace, без TLS/AUTH в коде), persistence/replication (вне материала), границы TB-1 (CacheManager↔Redis), TB-3 (↔shared DB).

Критический путь: `consumer → getOrLoad → redis.GET (miss) → loader() → redis.SET → return`; `consumer → get → redis.GET (null) → JSON.parse → THROW`.

[REFACTORING] Option B (рекомендуется): constructor-injected ioredis + config (prefix, defaultTtlMs, lockTtlMs, negativeTtlMs). `set()` с `PX` TTL. `getOrLoad()` с in-process single-flight Map + distributed lock (SETNX+TTL) + negative caching. `invalidateAll()` через `SCAN`+`UNLINK` scoped to prefix. try/catch + fallback to loader. Circuit breaker + metrics hooks. Option A (minimal) отклонён: оставляет namespace-риск открытым. Option C (library replacement) не оценён по конкретным библиотекам — кандидат для повторного рассмотрения.

[PARALLELS] Cache-aside без single-flight — классический thundering herd (ср. Facebook memcache lease, Redis `SET NX` lock pattern). `KEYS *` в проде — известный анти-паттерн (Redis docs: O(N), блокирует сервер). Отсутствие TTL — стандартный источник OOM в кэш-слоях.

[TESTS] 0% покрытие. Нужно: unit (set/get/getOrLoad с моком ioredis), unit `get()` на missing key → null (не throw), concurrency (N параллельных getOrLoad → loader вызван один раз), integration (Redis down → fallback, без unhandled rejection), integration (`invalidateAll` на 1M ключей → SCAN завершается), edge (falsy cached values 0/''/false — использовать `cached !== null`, не `if (cached)`), edge (несериализуемые значения).

[ACTION]
- **NOW** — заменить `KEYS *` на `SCAN`+`UNLINK`; добавить TTL в `set()`; обернуть все Redis-вызовы в try/catch; `get()` возвращает `null` при отсутствии ключа.
- **TODAY** — ввести namespace prefix; in-process single-flight для `getOrLoad`; метрики hit/miss/error.
- **TOMORROW** — DI через конструктор; distributed lock (если multi-instance); circuit breaker; negative caching с низким TTL.
- **LATER** — миграция старых ключей (SCAN+UNLINK после cutover); SLO + алерты + runbook.

[QUESTIONS]
1. Deployment topology: single-instance или multi-instance? Определяет, нужен ли distributed lock или достаточно in-process single-flight.
2. Redis shared с другими сервисами (сессии/очереди/rate-limit)? Определяет критичность namespace.
3. Есть ли метрики p99 loader duration? `lockTtlMs=4000` — ASSUMPTION (p99_hold_ms=2000 × safety_factor 2), не измерено.
4. Версия ioredis и наличие CVE? Нет lockfile/package.json в материале.
5. Redis persistence/replication config (RDB/AOF, replica)? Влияет на семантику `invalidateAll`.

[FUNC:FULL]
- **ECON**: effort ~1–2 дня (Option B), cost $0 (code-level fix), ROI высокий (предотвращение OOM/каскадного отказа), budget не задан, cloud delta 0 (размер Redis не меняется; TTL может снизить память → потенциальное снижение cost), cost of delay — риск прод-инцидента (OOM, cross-tenant deletion) ежедневно.
- **FAIL**: критично — Redis down → unhandled rejection (FP-1); `KEYS *` → блокировка Redis (FP-2); stampede → перегрузка origin (FP-3); нет TTL → OOM (FP-4). Cascade: Redis деградация → app latency = Redis latency → origin получает всю нагрузку → каскадный отказ downstream. Recovery: откат кода возможен, но удалённые ключи (сессии/очереди) не восстановимы; OOM требует ручного вмешательства.
- **METRICS**: codebase ~35 строк, 1 класс, 4 метода; deps 1 (ioredis, версия неизвестна); tests 0%; perf — `KEYS *` O(N) блокирующий, `DEL` в цикле N round-trips; quality — 4 аннотированных бага, `any` типы, нет error handling; infra — pool_size=50 (ASSUMPTION), timeout ≤10s (binding constraint), lockTtlMs=4000 (ASSUMPTION).
- **ALTERNATIVES**: языки — n/a (TS); фреймворки — Option A (minimal hardening, отклонён), Option B (hardened+namespaced+DI, рекомендуется), Option C (library replacement: cache-manager+keyv, node-cache+Redis adapter — не оценён по конкретным библиотекам); БД — Redis (не меняется); инфра — отдельная Redis DB/instance для кэша vs shared (namespace обязателен при shared); паттерны — cache-aside + single-flight + circuit breaker + negative caching.
- **EVOLVE**: coupling 2/10 (tight to concrete ioredis, module-level singleton); abstractions 2/10 (нет interface, `any` типы); growth 3/10 (feature_add); friction высокий (нет DI → тесты сложны, нет namespace → cross-tenant риск). Option B поднимает до ~7/10.
- **COMPARE**: Option A — time ~0.5 дня, cost $0, risk средний (namespace-риск открыт), complexity низкая. Option B — time ~1–2 дня, cost $0, risk низкий, complexity средняя. Option C — time ~2–3 дня (миграция), cost $0, risk средний (dependency risk), complexity средняя.

[MANDATORY BASE]
1. **ECONOMICS**: time ~1–2 дня (Option B), cost $0 (code-level fix), при условии что deployment topology известна и метрики p99 loader доступны для калибровки lockTtlMs.
2. **RISKS**: критично — `KEYS *` DoS, stampede, OOM без TTL, Redis down = app down; важно — cross-tenant deletion, нет TLS/AUTH, нет observability; при условии что Redis shared и на горячем пути.
3. **INFRASTRUCTURE**: pool_size=50, при условии что это дефолт ioredis и не переопределён (в материале не видно); timeout ≤10s (binding constraint), lockTtlMs=4000 (ASSUMPTION: p99_hold_ms=2000 × safety_factor 2).
4. **CODE**: change ~35 строк → ~120 строк (Option B), при условии что API конструктора меняется (breaking change для `new CacheManager()`).
5. **ACTION**: now — SCAN+UNLINK, TTL, try/catch, null-safe get; tomorrow — namespace, single-flight, метрики, DI.
6. **TIMELINE**: NOW — hotfix критичных багов (KEYS *, TTL, error handling); TODAY — namespace + single-flight + метрики; TOMORROW — DI + circuit breaker + negative caching; LATER — миграция ключей, SLO, алерты, runbook.
7. **PRODUCTION IMPACT**: users — все потребители shared Redis DB + downstream origin (точное N неизвестно, нет метрик); deploy window — требуется окно для breaking change конструктора; rollback — откат кода возможен, но удалённые ключи не восстановимы, OOM требует ручного вмешательства.
8. **SLO IMPACT**: current — SLO не определены (0%); after — рекомендуется availability 99.9%, p99 get/set < 50ms, hit ratio > 70%, при условии что метрики внедрены.
9. **CLOUD COST**: current $N неизвестно (нет infra spec); projected $N неизвестно; delta ±$0 (размер Redis не меняется; TTL может снизить память → потенциальное снижение).
10. **ON-CALL**: new alerts — Redis down, latency spike > 50ms p99, error rate > 1%, keyspace > 80% maxmemory, loader calls per key > 5/min, invalidateAll duration > 5s; runbook — отсутствует, требуется создать; escalation — level 2 (return_to_stage2 по stage4).

[REFLEXION]
1. **Слабое место**: `lockTtlMs=4000` основан на ASSUMPTION p99_hold_ms=2000 без метрик → **исправлено**: помечено как ASSUMPTION в [MANDATORY BASE] п.3 и в [QUESTIONS] п.3, требуется измерение перед фиксацией.
2. **Слабое место**: deployment topology неизвестна, но рекомендация включает distributed lock → **исправлено**: в [QUESTIONS] п.1 и [ACTION] TOMORROW указано условие "если multi-instance"; collision в stage4 зафиксирован.
3. **Слабое место**: Option C (library replacement) отклонён без оценки конкретных библиотек → **исправлено**: в [REFACTORING] и [FUNC:FULL] ALTERNATIVES указано "не оценён по конкретным библиотекам — кандидат для повторного рассмотрения".
4. **Слабое место**: stage4 содержит `force_emergency: true` и `return_to_stage2: true` — это сигнал, что анализ не завершён → **исправлено**: отражено в [CONCLUSION] ("требуется верификация") и [MANDATORY BASE] п.10 (escalation level 2).

Итог: **needs_refinement** — stage4 вернул `force_emergency: true` и `return_to_stage2: true`; два критических collision (namespace vs Option A, stampede scope vs unknown topology) требуют повторного анализа stage2 с deployment context. Финальный Markdown выдан с явными VERIFY-флагами, но полная уверенность недостижима без внешних данных.

---

**Примечание**: `[AUDIT_TRAIL]` не генерируется — добавляется pipeline'ом автоматически. `loss_pct` не рассчитан вручную — требуется `python tools/fallback_check.py --level D2 --present "[ECHO],[ROUTE],[CONCLUSION],[RISK_NODES],[ASSEMBLY],[REFACTORING],[PARALLELS],[TESTS],[ACTION],[QUESTIONS],[FUNC:FULL],[MANDATORY BASE]"`.

[AUDIT_TRAIL]
audit_id: audit-2026-10-10-c36a89
material_hash: sha256:8d8cfd52ac4e19edb079a3ffa81d503b4c446d05f8e1e08d7c1f185f4bb9cda0
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

    vishap analyze data/real_cases/own/cache_manager.ts
