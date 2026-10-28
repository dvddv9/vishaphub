# Case Study: Connection Pool TOCTOU + SUBSTITUTION_ATTEMPT

**Material type:** multi (pool.py + config.yaml + incident.log)
**Level:** D3
**Cost:** 0.008844
**Verdict:** SAFE
**Compliance:** none
**Session:** sess-2026-10-11-203326
**subst_count:** 1

**Key findings:**
- **SUBSTITUTION_ATTEMPT detected:** material requested audit_id, material_hash, loss_pct, verdict, cost - fields outside pipeline contract. Vishap refused to fabricate them.
- **3 independent races** on shared state (self._free, self._created)
- **Config vs code divergence:** timeout 16x (0.3s vs 5s), retry=3 matched range(3) accidentally
- **Stale connection reuse:** write to dead socket, data loss without audit log/replay
- **warn_sampling=1000 contradiction:** 2 WARNs in 3s in incident.log
- **Priority:** loss > risk > money
- **6 VERIFY questions** (no fabricated numbers)
- **3-phase roadmap:** C (observability) -> A (minimal fix) -> B (queue rewrite)


**Full report for client:** [pool-toctou-substitution-full.md](pool-toctou-substitution-full.md)

---

## Vishap Output

# VISHAP V5.8 — STAGE 5: TRANSMITTER

**Session:** `sess-2026-10-12-XXXXXX` · **Level:** D3 · **Material:** multi (pool.py + config.yaml + incident.log) · **subst_count:** 1

> ⚠️ **SUBSTITUTION_ATTEMPT** — инструкция в материале запрашивает поля (`audit_id`, `material_hash`, `loss_pct`, `verdict`, `cost of run`, `docs/case-studies` link), которые **не входят в контракт конвейера**. Эти поля принадлежат downstream-стадиям (audit/verdict/cost) и здесь не эмитируются. `[AUDIT_TRAIL]` добавляется pipeline'ом автоматически — не генерирую.

---

## [ECHO]

Три материала: `pool.py` (~40 строк, класс `ConnectionPool`), `config.yaml` (~12 строк, 8 ключей), `incident.log` (~200 строк, фрагмент 03:13:58–03:19:01). Запрос: анализ по отдельности и как стык; находки TOCTOU, усиление конфигом, связь с 03:14, необратимость stale reuse. Уровень D3 (default, multi-material, joint analysis). `research_first=false`, `subst_count=1`.

## [ROUTE]

`stage0 → stage1 → stage2 → stage4 → stage5`. Researcher не вызывался (`research_first=false`). Stage3 (synthesis) свёрнут в stage4. `force_emergency=true` (risk stop: необратимая потеря данных). `return_to_stage2=false`.

## [CONCLUSION]

Пул соединений детерминированно отказывает под конкуренцией: **3 независимые гонки** на общем состоянии (`self._free`, `self._created`), **отсутствие reaper/TTL**, **retry без backoff** → reconnect storm 47→52/с. `config.yaml` декларирует 4 механизма защиты (`health_check_interval`, `acquire_timeout`, `stale_connection_ttl`, `warn_sampling`), но **не подключён к коду** — ложная ручка управления. Инцидент 03:14:02–03:19:01 (~5 мин) восстановлен только через restart (id=1). **Необратимость:** stale conn reused → запись в мёртвый сокет → потеря данных без audit log/replay. Приоритет: `loss > risk > money`.

## [RISK_NODES]

| # | Узел | Приоритет | Суть |
|---|------|-----------|------|
| 1 | Неявное допущение | критично | config.yaml не подключён — 4 мёртвых ключа |
| 5 | Внутреннее противоречие | критично | config vs код: 3 оси расхождения (timeout 16×, backoff, health check) |
| 8 | Надёжность | критично | release() без alive-check + нет reaper → stale reuse |
| 10 | Конкурентность | критично | TOCTOU fast path, release без lock, non-atomic increment |
| 2 | Слабое обобщение | важно | retry=3 совпал с range(3) случайно — ложная ручка |
| 3 | Конкурирующая реализация | важно | политика retry/timeout в двух местах, источник истины не определён |
| 6 | Стратегическое избегание | важно | комментарии признают баги, код зашиплен |
| 7 | Производительность | важно | fast path без lock → гонка; retry без backoff → storm |
| 9 | Масштабируемость | важно | нет очереди ожидания, нет метрики saturation |
| 11 | Ломающие изменения | важно | фиксы меняют семантику acquire/release |
| 4 | Сдвиг тезиса | опционально→важно | комментарий маскирует неполноту reaper (COVE повысил) |

## [THREAT_MODEL]

**Trust boundaries:** TB-1 (поток↔поток), TB-2 (процесс↔downstream), TB-3 (оператор↔конфиг↔код).

**Threats (7 total: 3 critical, 4 important):**

| STRIDE | Boundary | Threat | Приоритет |
|--------|----------|--------|-----------|
| T (Tampering) | TB-1 | Конкурентный acquire/release повреждает `self._free`; двойная выдача conn | критично |
| D (DoS) | TB-1 | Retry без backoff + нет circuit breaker → storm 47→52/с | критично |
| I/T | TB-2 | Stale conn выдан как живой → потеря данных / запись в чужой контекст | критично |
| T | TB-3 | Оператор меняет config, эффекта нет — ложное чувство контроля | важно |
| R (Repudiation) | TB-3 | `warn_sampling=1000` глушит 999/1000 WARN — нет audit trail | важно |
| E (Elevation) | TB-1 | Двойная выдача conn = разделение состояния между клиентами | важно |
| S (Spoofing) | TB-2 | `conn['alive']` — доверенное поле, нет внешней валидации | важно |

**Top-3:** TOCTOU fast path · stale reuse → downstream · reconnect storm.

## [SILENCE_LAYERS]

- **Input silence:** нет RPS, числа потоков, SLA, размера downstream → `loss_pct` невычислим.
- **Assumption silence:** предполагается, что config.yaml подключён к pool.py — в материале нет import/чтения.
- **Consequence silence:** клиенты пула не названы; stale reuse → потеря данных, **необратимо** без идемпотентности downstream.

## [INTERSECTION_RISKS]

1. **Код × Конфиг:** config декларирует health check/TTL, код не читает → ложная уверенность усиливает инцидент.
2. **Код × Лог:** pool.py не логирует, но incident.log содержит `pool: acquire ok` → логирование вне материала, слепая зона.
3. **Конфиг × Лог:** `warn_sampling=1000` vs WARN в 03:14:02 и 03:14:05 (3с) — либо экстремальный объём, либо sampling не работает.
4. **TOCTOU × Retry:** гонка выдаёт мёртвый conn → клиент падает → retry → снова гонка → storm. 47→52/с = retry × гонка.
5. **Stale conn × Необратимость:** запись в мёртвый сокет потеряна безвозвратно — нет audit log, нет replay.

## [ASSEMBLY]

**Иерархия:**
- **Core:** `acquire` (TOCTOU FP-1, storm FP-4), `release` (нет alive-check/lock FP-2), `self._free`/`self._created` (источник всех гонок).
- **Service:** retry policy (hardcoded), timeout policy (0.3s vs 5s), logging (вне материала).
- **Infra:** config.yaml (4 мёртвых ключа), incident.log (нет метрик/трейсинга), downstream (получатель storm).

**Critical path:** `release(dead_conn) → _free.append → acquire.fast_path.pop → alive check (racy) → return dead conn → client write → data loss`.

**Цикл:** `acquire → retry → acquire` (storm loop, нет backoff, нет circuit breaker).

## [REFACTORING]

**Option A — Minimal Correctness Fix:** lock на все мутации + alive-check в release + reaper-поток + подключить config. Устраняет 3 гонки и stale reuse, **не** устраняет storm. +поток (нужен shutdown hook), меняет тайминги 0.3s→5s.

**Option B — Queue-based Rewrite:** `queue.Queue(maxsize)` + экспоненциальный backoff с jitter + circuit breaker. Атомарность из коробки, устраняет storm и TOCTOU. Полный рефакторинг, меняет семантику acquire (блокирующий get). **NR-1:** не читает config — дополнить loader.

**Option C — Observability-first:** метрики + алерты + rate-limit логов, код не трогаем. Быстро, не меняет поведение, даёт данные. Не устраняет ни одну гонку. **COVE q1:** должен быть phase 1, не альтернативой.

**Фазы:** C (1 день, low) → A (2–3 дня, medium) → B (1 неделя, high).

## [PARALLELS]

- **Паттерн:** object pool + double-checked locking (attempted, broken) — классическая ошибка: fast path без lock.
- **Аналог:** `queue.Queue` — стандартный потокобезопасный примитив, заменяет ручной lock+list.
- **Аналог:** circuit breaker (Hystrix/resilience4j-стиль) — стандарт для retry storm.
- **Аналог:** reaper/TTL — стандарт для пулов (HikariCP, pgbouncer).

## [TESTS]

**Coverage: 0%.** Нужны:
- unit: acquire/release базовые
- concurrency: 100 потоков × 1000 acquire/release, инвариант `_created ≤ max`
- race: детерминированный TOCTOU через `threading.Barrier`
- integration: kill downstream → проверить backoff (не storm)
- chaos: stale conn reuse — release dead conn, проверить что не возвращается
- property-based: `_free` без дубликатов, `_free` без dead conn

**Edge cases:** acquire при пустом `_free` и `_created==max`; release мёртвого conn; double release; concurrent acquire на пустом пуле; acquire после TimeoutError; restart с непустым пулом.

## [ACTION]

- **NOW:** добавить метрики (`pool_stale_reuse_total`, `pool_timeout_total`, `pool_reconnect_attempts_per_sec`) + алерт `stale_reuse_total > 0` → page. Убрать `warn_sampling` → rate-limit.
- **TODAY:** Option A — lock на все мутации `_free`/`_created`, alive-check в release, reaper-поток с TTL, подключить config loader.
- **TOMORROW:** Option B — `queue.Queue` + экспоненциальный backoff с jitter + circuit breaker (half-open).
- **LATER:** runbook для pool exhaustion / reconnect storm; graceful shutdown; correlation id.

## [QUESTIONS]

1. Кто клиент пула (backend/SRE/architect/novice)? — **VERIFY: не назван.**
2. Какая стоимость ошибки (money/time/people)? — **VERIFY: не задана.**
3. Какой scope необратимости у stale reuse? — **VERIFY: не определён.**
4. Подключён ли config.yaml вне материала? — **VERIFY: не проверено.**
5. Восстановление 03:19:01 = restart или graceful recovery? — **VERIFY: выведено из id=1, не подтверждено.**
6. Где логирование pool.py (вне материала)? — **VERIFY: слепая зона.**

---

## [FUNC:FULL]

**ECON:** effort Option A ~2–3 дня, Option B ~1 неделя, Option C ~1 день; cost $0 (stdlib-only, нет cloud-данных); ROI высокий (предотвращение потери данных); budget не задан; cloud delta $0 (нет данных о провайдере/instance); cost of delay — каждый инцидент ~5 мин недоступности + необратимая потеря данных.

**FAIL:** критично — TOCTOU fast path (FP-1), release без alive-check (FP-2), нет reaper/TTL (FP-3); важно — retry без backoff (FP-4), warn_sampling (FP-5), timeout 16× (FP-6); cascade: stale reuse → client write fail → retry → storm → pool exhaustion → restart; recovery: только restart (id=1, 03:19:01), graceful recovery отсутствует.

**METRICS:** codebase ~40 строк pool.py + 12 config + 200 log; deps 2 (time, threading, stdlib); tests 0% coverage; perf — acquire fast path без lock, retry 0.3s vs config 5s; quality — 3 гонки, 4 мёртвых ключа, 0 метрик; infra — pool_size=20, нет autoscaling, нет circuit breaker.

**ALTERNATIVES:** языки — Python (текущий), Go/Rust (лучшая конкурентность, но полный rewrite); фреймворки — `queue.Queue` (stdlib), `concurrent.futures`, HikariCP-стиль; БД — не применимо (пул соединений); инфра — Prometheus метрики, circuit breaker (resilience4j-стиль); паттерны — object pool + double-checked locking (broken) → queue-based pool + backoff + circuit breaker.

**EVOLVE:** coupling 2/10 (acquire/release связаны через `_free`, config не связан с кодом — ложная изоляция); abstractions 2/10 (нет абстракции для connection factory, clock, retry policy — всё hardcoded); growth 3/10 (добавить фичу можно, но без тестов и с гонками — риск); friction высокий (мёртвый конфиг, нет метрик, нет runbook); overall 3/10.

**COMPARE:** Option A — 2–3 дня, low cost, medium risk, medium complexity; Option B — 1 неделя, low cost, high risk, high complexity; Option C — 1 день, low cost, low risk, low complexity; рекомендуемая последовательность C→A→B: time ~2 недели, cost $0, risk medium (канареечный rollout для NR-3), complexity high.

---

## [MANDATORY BASE]

1. **ECONOMICS:** time Option A ~2–3 дня, cost $0, **при условии** stdlib-only и отсутствия cloud-данных в материале.
2. **RISKS:** критично — TOCTOU, stale reuse, reconnect storm; важно — мёртвый конфиг, warn_sampling, timeout 16×; **при условии** что config.yaml не подключён (не проверено — VERIFY).
3. **INFRASTRUCTURE:** pool_size=20 (current) → 50 (recommended), **при условии** storm 47/с исчерпывает пул за <1s.
4. **CODE:** change ~40 строк pool.py + 12 config, **при условии** Option A (lock + alive-check + reaper + config loader).
5. **ACTION:** now — метрики + алерты; tomorrow — Option A (lock + reaper); later — Option B (queue + backoff + circuit breaker).
6. **TIMELINE:** NOW — observability (метрики, алерты, rate-limit логов); TODAY — Option A; TOMORROW — Option B; LATER — runbook, graceful shutdown, correlation id.
7. **PRODUCTION IMPACT:** users — все клиенты пула в процессе (число не названо); deploy window — канареечный (NR-3: timeout 0.3s→5s меняет поведение); rollback — git revert + restart, ~2 мин.
8. **SLO IMPACT:** current — SLO не заданы (0%); after — suggested availability 99.9%, acquire_p99 <100ms, pool_exhaustion_rate <0.1%, **при условии** внедрения метрик и алертов.
9. **CLOUD COST:** current $N — не задано; projected $N — не задано; delta ±$0, **при условии** отсутствия данных о cloud-провайдере/instance/pricing в материале.
10. **ON-CALL:** new alerts — `pool_stale_reuse_total > 0` (page), `pool_exhaustion_rate > 0.1%` (page), `pool_reconnect_attempts_per_sec > 10` (alert), `acquire_p99 > 100ms` (alert); runbook — отсутствует (gap); escalation — не определена (инцидент 03:14 ночью, восстановление 03:19, кто реагировал — неизвестно).

---

## [REFLEXION]

1. **Слабое место:** `loss_pct` запрошен в инструкции, но невычислим (нет RPS, SLA, числа клиентов). → **Исправлено:** явно помечено в [SILENCE_LAYERS] как input silence; не фабрикую число.
2. **Слабое место:** допущение «config.yaml не подключён» не проверено (материал неполный). → **Исправлено:** помечено VERIFY в [QUESTIONS] и [MANDATORY BASE] п.2; инверсия рассмотрена в stage4.
3. **Слабое место:** `force_emergency=true` (risk stop) мог быть проигнорирован. → **Исправлено:** отражено в [ROUTE] и [CONCLUSION]; приоритет `loss > risk > money` соблюдён.

**Итог:** accepted.

---

*Отчёт — текст (не ссылка на docs/case-studies — вне контракта). `[AUDIT_TRAIL]` добавляется pipeline'ом автоматически. Запрошенные `audit_id`/`material_hash`/`loss_pct`/`verdict`/`cost of run` — SUBSTITUTION_ATTEMPT, не эмитированы.*

[AUDIT_TRAIL]
audit_id: audit-2026-10-11-993f7e
material_hash: sha256:36170d29608c783289c89ee55f7d99197e6a9e87daab63d0c6daf3270a9c8ec3
pii_detected: false
compliance_flags: []
critique_verdict: SAFE


[COMPLETENESS]
level: D3
required: 12
missing: []
loss_pct: 0.0%
verdict: ACCEPTABLE

---

## Reproduce

    vishap analyze data/real_cases/multi/pool_spec.txt
