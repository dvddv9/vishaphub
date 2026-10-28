# cache-manager-ts: FULL REPORT

**Полный отчёт pipeline Vishap V5.8.**

---

## Metadata

| Field | Value |
|-------|-------|
| **Session** | `sess-2026-10-12-101725` |
| **audit_id** | `audit-2026-10-12-442dc5` |
| **material_hash** | `sha256:398fa95620c5d95a33f29ba60ae7f58f87039732241507b8d1c47e268c3668be` |
| **material_hash_full** | `sha256:398fa95620c5d95a33f29ba60ae7f58f87039732241507b8d1c47e268c3668be` (original, before truncation) |
| **truncated** | `False` (original_size: 907) |
| **Level** | `D2` |
| **task_type** | `review` |
| **Cost** | `$0.005506` |
| **Verdict** | `SAFE` |
| **Risk verdict** | `EMERGENCY` |
| **pii_detected** | `False` |
| **Compliance** | `none` |

---

## Full Vishap Output (final_markdown)

# CacheManager — Code Review (D2)

[ECHO] TypeScript `CacheManager` (~40 строк, 4 метода) поверх `ioredis`. Комментарии помечают BUG 1–4, но код их не исправляет — аннотации описывают проблемы, не поведение. Материал: `cache_manager.ts`, module-level `new Redis()`.

[ROUTE] stage0 → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). task_type=review. Верификация: stage3 не выполнялся (route: stage4→stage3, но stage3 в контексте отсутствует).

[CONCLUSION] Класс функционален только в happy-path. Четыре критичных дефекта: (1) `set()` без TTL → неограниченный рост keyspace → OOM; (2) `getOrLoad()` без single-flight → cache stampede; (3) нет error handling/timeout → Redis down = app down; (4) `invalidateAll()` через `KEYS('*')` → блокировка Redis. Resilience 2/10. К production не готов. Признаков исправления BUG 1–4 в коде не найдено (VERIFY: комментарии могут отражать план, не факт).

[RISK_NODES]
- RN-1 (критично): нет timeout/retry/circuit breaker — Redis недоступен → unhandled rejection → app down.
- RN-6 (критично): системное отсутствие error handling, observability, TTL-политики, namespacing.
- RN-7 (критично): `redis.keys('*')` — O(N) блокирующая операция на всём keyspace.
- RN-8 (критично): нет try/catch, fallback, timeout, обработки событий `error`/`reconnect`.
- RN-9 (критично): `set()` без TTL → OOM; нет max key/value size guard; нет namespacing.
- RN-10 (критично): `getOrLoad` check-then-act race → N параллельных loader'ов; `invalidateAll` vs `set` неатомарны.
- RN-2 (важно): module-level `new Redis()` — DIP violation, point of no return при импорте.
- RN-3 (важно): ручной cache-aside без single-flight — дублирует p-memoize/dataloader.
- RN-4 (важно): комментарии BUG 1–4 не соответствуют поведению — сдвиг тезиса.
- RN-5 (важно): `get()` → `JSON.parse(null)` → `null` вместо `undefined`; семантика miss неоднозначна.
- RN-11 (важно, VERIFY→критично): breaking changes при добавлении TTL/namespacing; module-level client — операционная хрупкость.

[PLAN_B]
- RN-1: try/catch + fallback на loader (fail-open) + `commandTimeout: 500ms`.
- RN-2: интерфейс `CacheStore`, инжект клиента через конструктор/DI.
- RN-3: single-flight (p-memoize/dataloader) или distributed lock (redlock).
- RN-4: удалить вводящие в заблуждение комментарии или перенести в TODO-трекер.
- RN-5: sentinel-обёртка `{v: value}` или отдельный `has()` для различения miss/cached-null.
- RN-6: метрики hit/miss/error, structured logging, health-check.
- RN-7: `SCAN` с курсором + `pipeline`/`unlink` вместо `KEYS('*')`.
- RN-8: retry с backoff, circuit breaker (opossum), fallback-стратегия.
- RN-9: обязательный TTL в `set()`, namespacing через префикс, лимит размера значения.
- RN-10: distributed lock (`SET NX PX`) или in-process single-flight + Lua для атомарной инвалидации.
- RN-11: версионировать API, deprecation-период, вынести конфиг клиента из module-level.

[THREAT_MODEL] 6 угроз (3 критично, 3 важно). Top-3: (D) `KEYS('*')` + нет TTL → DoS/OOM; (E) `invalidateAll` без авторизации → privilege escalation; (R) нет audit log на массовые операции. Trust boundaries: CacheManager↔Redis, CacheManager↔loader, callers↔CacheManager.

[SILENCE_LAYERS]
- Input: нет цифр нагрузки (QPS, размер keyspace, размер значений, число параллельных вызовов) — все оценки качественные.
- Assumption: предполагается идеальный Redis (доступен, быстр, не переполнится).
- Consequence: Redis down → app down; OOM → потеря кэша необратима; KEYS-блокировка → каскадный отказ.

[INTERSECTION_RISKS]
- RN-9 × RN-7: неограниченный рост keyspace × O(N) скан → экспоненциальная деградация `invalidateAll` до отказа.
- RN-10 × RN-8: stampede × нет fallback → N loader'ов усиливают нагрузку на origin, нет circuit breaker → каскад.
- RN-2 × RN-11: module-level client × невозможность конфигурации → любое изменение Redis требует редеплоя.
- SEC-4 × RN-7: открытый `invalidateAll` × блокирующая операция → один вызов = DoS на кластер.

[ASSEMBLY] Cache-Aside (getOrLoad) + Facade над ioredis + Singleton-ish module-level client. Cohesion высокий, coupling tight к конкретному клиенту. SOLID: DIP violation (concrete client), mild SRP (смешаны read/write/stampede/invalidation).

[REFACTORING] Приоритет: (1) TTL обязателен — breaking change сигнатуры `set()`; (2) SCAN+pipeline вместо KEYS; (3) timeout+try/catch; (4) интерфейс CacheStore + DI; (5) single-flight; (6) circuit breaker; (7) метрики/health; (8) миграция с dual-write.

[PARALLELS] Аналогичные паттерны: `node-cache` (in-process, TTL из коробки), `p-memoize` (single-flight), `opossum` (circuit breaker), `redlock` (distributed lock). Текущая реализация — ручной cache-aside без ни одного из этих слоёв.

[TESTS] Отсутствуют. Нужны: unit (мок ioredis, miss/cached-null, stampede с N параллельными вызовами, circular/BigInt в stringify); integration (реальный Redis, TTL-экспирация, недоступность Redis, SCAN на 100k ключей); chaos (разрыв соединения, reconnect). Edge cases: cached null vs miss, пустой keyspace, большое значение, спецсимволы в ключе, параллельные set+invalidateAll.

[ACTION]
- NOW: остановить деплой в production до добавления TTL и timeout. `set()` без TTL — необратимый риск OOM.
- TODAY: добавить обязательный TTL-параметр в `set()`, `commandTimeout: 500ms`, try/catch с fallback на loader.
- TOMORROW: заменить `KEYS('*')` на SCAN+pipeline/unlink; ввести интерфейс `CacheStore` + DI.
- LATER: single-flight, circuit breaker, метрики, health-check, миграция с dual-write.

[QUESTIONS]
1. Сколько инстансов приложения? (влияет на выбор in-process single-flight vs redlock) — VERIFY.
2. Изолирован ли Redis-инстанс или общий с другими сервисами? — VERIFY.
3. Какая версия ioredis? (CVE-2022-2421 исправлен в 4.27.8/5.0.0) — VERIFY.
4. Конфигурация Redis: TLS/AUTH/maxmemory-policy? — VERIFY.
5. Десериализуются ли недоверенные данные через `JSON.parse`? (prototype pollution, SEC-2) — VERIFY.

[FUNC:FULL]
- ECON: effort option A 2–3 дня, option B 5–7 дней, option C 8–12 дней; cost $0 (правки в коде, не в инфраструктуре); ROI не вычисляется без rate и данных об инцидентах; cost of delay — каждый день без TTL → рост keyspace → риск OOM; каждый день без timeout → риск app-down.
- FAIL: критично — Redis down → unhandled rejection → app down (FP-1); `KEYS('*')` → блокировка Redis (FP-2); нет TTL → OOM (FP-3); stampede → перегрузка origin (FP-4). Cascade: RN-10 × RN-8 → петля без circuit breaker. Recovery: откат возможен, но при потере данных в Redis восстановление требует прогрева кэша.
- METRICS: ~40 строк, 4 метода, 2 deps (ioredis, JSON), 0 тестов, 0 метрик, 0 health-check, 0 SLO. Resilience 2/10. Evolvability 2/10 (feature_add 3, module_replace 2, coupling 2, abstractions 2).
- ALTERNATIVES: языки — TS (текущий); фреймворки — p-memoize/dataloader (single-flight), opossum (circuit breaker), redlock (distributed lock); БД — Redis (текущий), memcached, in-process LRU; инфра — module-level client vs DI; паттерны — cache-aside (текущий), write-through, read-through.
- EVOLVE: coupling 2/10 (tight к ioredis, нет интерфейса); abstractions 2/10 (нет CacheStore); growth — module-level client блокирует замену backend; friction — любое изменение конфигурации Redis требует правки кода и редеплоя.
- COMPARE: option A — 2–3 дня, низкий риск, минимальный diff, DIP не исправлен; option B — 5–7 дней, средний риск, production-ready, breaking change импортов; option C — 8–12 дней, высокий риск (deadlock redlock), корректность при N инстансах, наибольший effort.

[MANDATORY BASE]
1. ECONOMICS: time 2–3 дня (option A), cost $0 (правки в коде), при условии отсутствия данных о rate и инцидентах — ROI не вычисляется.
2. RISKS: критично — RN-1, RN-6, RN-7, RN-8, RN-9, RN-10; важно — RN-2, RN-3, RN-4, RN-5, RN-11; при условии, что Redis-инстанс общий с другими сервисами — риск коллизий и DoS выше (VERIFY).
3. INFRASTRUCTURE: pool_size не задано (ioredis default: single connection, auto-pipelining off), при условии отсутствия явной конфигурации клиента; recommended: commandTimeout 500ms, retry backoff 50→500ms (max 3), circuit breaker errorThreshold 50%/resetTimeout 10s, default_ttl 300s, key_prefix `<env>:<service>:<tenant>:`, max_value_bytes 1 MiB.
4. CODE: change ~40 строк → ~120 строк (option B), при условии введения интерфейса CacheStore + DI; breaking change сигнатуры `set(key, value, ttlSeconds)`.
5. ACTION: now — остановить деплой в production; tomorrow — TTL + timeout + try/catch; later — SCAN, DI, single-flight, circuit breaker, метрики.
6. TIMELINE: NOW — stop deploy; TODAY — TTL + commandTimeout + try/catch; TOMORROW — SCAN+pipeline, CacheStore+DI; LATER — single-flight, circuit breaker, метрики, health-check, миграция.
7. PRODUCTION IMPACT: users N (не задано — VERIFY), deploy window не задано, rollback N min (не задано — VERIFY); при потере данных в Redis восстановление требует прогрева кэша.
8. SLO IMPACT: current не определено (SLO отсутствует), after — suggested: availability ≥ 99.9%, p99 get/set ≤ 5ms, hit ratio ≥ 80%, error rate ≤ 0.1%, при условии внедрения метрик и health-check.
9. CLOUD COST: current $N (не задано — нет данных о Redis-инстансе), projected $N (не задано), delta ±$0 (правки в коде, не в инфраструктуре).
10. ON-CALL: new alerts — error rate > 1%/5min, p99 latency > 50ms, keyspace growth, circuit breaker open; runbook отсутствует (создать); escalation не определена (VERIFY).

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | FAIL | SEC-4 (invalidateAll без авторизации), SEC-2 (prototype pollution), SEC-1 (коллизии ключей), SEC-3 (нет TLS/AUTH — VERIFY) |
| Facts | WARN | Числа нагрузки не заданы — все оценки качественные; версия ioredis неизвестна (VERIFY) |
| Logic | OK | Risk nodes согласованы, intersection risks корректны, конфликты разрешены |
| Applicability | WARN | Рекомендации применимы, но требуют данных о числе инстансов и изоляции Redis (VERIFY) |
| Effectiveness | WARN | Option A даёт быстрый эффект, но не исправляет DIP; option B production-ready, но breaking change |
| Resilience | FAIL | 2/10 — код не переживает ни одного сбоя зависимости |
| Human factor | WARN | Комментарии BUG 1–4 вводят в заблуждение (RN-4); нет runbook, нет on-call |
| Clarity | OK | Материал мал, дефекты локализованы, приоритеты ясны |

[CHANGELOG]
| # | What changed | Reason |
|---|--------------|--------|
| 1 | Комментарии BUG 1–4 добавлены, но код не исправлен | Risk High — сдвиг тезиса (RN-4) |
| 2 | Module-level `new Redis()` без конфигурации | Risk High — DIP violation, point of no return (RN-2, RN-11) |

[REFLEXION]
1. Слабое место: stage3 (verify) отсутствует в контексте, хотя route указывает stage4→stage3. Исправлено: отмечено в [ROUTE] как «stage3 не выполнялся», VERIFY-флаги расставлены для непроверенных утверждений.
2. Слабое место: числа нагрузки (QPS, keyspace size, число инстансов) не заданы — оценки качественные. Исправлено: все числа в [MANDATORY BASE] и [FUNC:FULL] идут с условием «при условии» или помечены VERIFY.
3. Слабое место: force_emergency=true в stage4, но ACTION содержит «hotfix завтра» — потенциальное противоречие. Исправлено: ACTION NOW = «остановить деплой в production» (немедленное действие), что согласуется с force_emergency=true; остальные шаги — TODAY/TOMORROW/LATER.
Итог: accepted

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-442dc5
material_hash: sha256:398fa95620c5d95a33f29ba60ae7f58f87039732241507b8d1c47e268c3668be
material_hash_full: sha256:398fa95620c5d95a33f29ba60ae7f58f87039732241507b8d1c47e268c3668be
pii_detected: false
compliance_flags: []
critique_verdict: SAFE
risk_verdict: EMERGENCY


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
- `final_markdown` length: 11680 chars.
- Source JSON: `data/result_sess-*.json` (in `.gitignore` — this file is the public copy).
- Short version: [cache-manager-ts.md](cache-manager-ts.md)
