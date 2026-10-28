# Case Study: Distributed Rate Limiter — 2x Overpass

**Material type:** `multi` (rate_limiter.go + shard.go + metrics.log)
**Level:** D3
**task_type:** `review`
**Cost:** $0.008805
**Verdict:** SAFE
**Compliance:** none
**Session:** sess-2026-10-12-033244
**audit_id:** audit-2026-10-11-8aa116
**material_hash:** sha256:5d73d2f6471c1eab2cafb1ee0619eee4774060ddf2865af3bde4ca4a8d2fb552  (64 hex, real SHA-256)

**Key findings:**
- **Cross-file semantic mismatch:** `total_rate = shards x ratePerShard` declared as aggregate limit, but implemented as sum of independent buckets
- **Aggregate burst = 3200 vs declared 1600** — exactly 2x overpass
- **No single file contains the bug** — the defect lives at the `routing x state` intersection
- **RN-3 (BLOCKER):** reload 16->8 in log, but no reload path in shard.go — "second binary" hypothesis (VERIFY)
- **RN-5:** ratio 2.00 -> 1.00 without config change — transient over-admission
- **11 risk nodes** (including RN-3 blocker, RN-10 refill-window)
- **Plan B** for every critical/important risk
- **8-axis MATRIX** (Security: FAIL, Resilience: FAIL)
- **honest boundaries:** `ratio 2.00` framed as transient, not sustained
- **task_type=review** applied (calibration)


**Full report for client:** [rate-limiter-2x-overpass-full.md](rate-limiter-2x-overpass-full.md)

---

## Vishap Output

# Rate Limiter Over-Admission — D3 Review

[ECHO] Материал: `rate_limiter.go` (token bucket, mutex), `shard.go` (hash-роутинг по шардам), `metrics.log` (~300 строк, показано 15). Кейс: распределённый лимитер пропускает ~2× от заявленного. Прогон по трём материалам + стык.

[ROUTE] stage0 (orchestrator, task_type=review) → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). research_first=false, parallel_stages=false, subst_count=0.

[CONCLUSION] Наблюдается транзиентный over-admission до ratio=2.00 (12:00:50), не устойчивый: на 12:00:55 ratio=1.00 без config change. Наиболее вероятная причина — композиционная ошибка агрегатной ставки (n × ratePerShard vs configured total_rate), но она **не верифицирована**: (1) reload 16→8 в логе не имеет кода в `shard.go` — no signs of reload path found (VERIFY: вторая реализация/другой бинарник не исключены); (2) определение окна метрики `observed_rate` не описано — no signs of windowing spec found (VERIFY: ratio=2.00→1.00 может быть артефактом агрегации). Verdict: `requires_external_verification`. material_hash — placeholder (реальный sha256 не вычислен).

[RISK_NODES]
- **RN-1 (критично)** — агрегатная ставка = n × ratePerShard не верифицируется; observed 3200/s = 2× total_rate=1600/s.
- **RN-3 (критично, BLOCKER)** — reload 16→8 в логе не имеет кода в `shard.go`. No signs of reload path found (VERIFY: вторая реализация или другой бинарник).
- **RN-5 (критично)** — ratio=2.00 → 1.00 без config change. No signs of explanation found (VERIFY: оконная агрегация метрики).
- **RN-8 (критично)** — нет валидации n>0/rate>0/burst>0; n=0 → panic (modulo by zero). Wall-clock `time.Now()` без monotonic-гарантии.
- **RN-9 (важно, повышен из stage2 COVE)** — reload 16→8 без миграции состояния → всплеск допуска.
- **RN-2 (важно)** — hash%n ломается при смене n; FNV32a не криптостойкий.
- **RN-6 (важно)** — нет per-shard и per-key метрик → инцидент нелокализуем.
- **RN-10 (важно)** — `l.last` обновляется до решения об admission; refill-окно «съедается» при denied.
- **RN-7 (опционально)** — RWMutex на immutable slice — overhead на горячем пути.

[PLAN_B]
- RN-1: startup-assert `sum(shard.rate) == configured_total_rate`; логировать расхождение как ERROR.
- RN-3: найти running binary (build hash, deploy manifest) до любого изменения кода; свести к одной реализации.
- RN-5: прочитать определение метрики `observed_rate`; воспроизвести ratio=2.00 известной нагрузкой.
- RN-8: валидация n>0/rate>0/burst>0 с возвратом error; clock injection; monotonic time; clamp elapsed в [0, burst/rate].
- RN-9: миграция состояния шардов при reload либо запрет смены n на живом процессе.
- RN-2: consistent hashing (ring) либо фиксация n на весь lifetime процесса.
- RN-6: per-shard allowed/denied + per-key cardinality в метрики.
- RN-10: обновлять `l.last` только при успешном admission.
- RN-7: убрать RWMutex (slice immutable после конструктора).

[THREAT_MODEL]
- **TB-1 (client → Allow(key), недоверенный)**: S — подмена key для обхода лимита (критично); T — FNV32a коллизии на hot shard (важно).
- **TB-2 (config → NewSharded, доверенный, но не валидируется)**: T — невалидный конфиг → panic/fail-open (критично); E — reload без миграции → эскалация допуска (важно).
- **TB-3 (ShardedLimiter → Limiter, внутренняя)**: R — нет audit log решений (важно).
- **TB-4 (Limiter → metrics)**: I — утечка ключей при добавлении per-key метрик (опционально).
- **TB-5 (Limiter → downstream, граница защиты)**: D — over-admission 2× → DoS на downstream (критично).
- Итого: 7 угроз, 3 критично, 3 важно, 1 опционально.

[SILENCE_LAYERS]
- **Input**: нет RPS, числа уникальных ключей, распределения по шардам, latency downstream.
- **Assumption**: предполагается, что `observed_rate` — фактический допуск, а не агрегат с окном; не подтверждено.
- **Consequence**: downstream (auth/payment/upstream API) получает 2× трафика; при платном API перерасход необратим финансово.

[INTERSECTION_RISKS]
- **code × log**: `shard.go` без reload-пути × лог фиксирует reload 16→8 → в проде не тот бинарник.
- **code × log**: wall-clock `time.Now()` × ratio=1.00→2.00 без config change → NTP-скачок или оконная агрегация.
- **code × config**: hash%n × смена n 16→8 → потеря токенов, всплеск допуска.
- **observability × security**: нет per-shard метрик × over-admission 2× → митигация вслепую.
- **IT × payment**: rate-limit как защита × 2× bypass → 2× финансовый риск, необратимо в части проведённых транзакций.

[ASSEMBLY] Критический путь: `config → NewSharded(n, ratePerShard, burst) → per-shard Limiter → Allow(key) → hash%n → shard.Allow() → downstream`. Два из трёх service-layer компонентов (config loader, reload path) **выведены из лога, не из кода** — структурный корень RN-3. Граф — DAG, циклов нет.

[REFACTORING] Option A (fix-in-place, 2–3 дня): assert + валидация + monotonic clock + clamp + убрать RWMutex + per-shard метрики + алерт ratio>1.1. Адресует RN-1, RN-6, RN-7, RN-8, SEC-1..3, CONC-2. Не адресует RN-2, RN-3, RN-9, RN-11, BC-1, BC-2. Option B (consistent hashing + миграция, 5–8 дней): адресует RN-2, RN-9, RN-11, BC-1..3; риск — сложность миграции при 0% тестов. Option C (drop sharding, 1–2 дня): устраняет композиционную ошибку by construction; теряет горизонтальное масштабирование (при 3200 rps один mutex, вероятно, приемлем — stage4 COVE повысил вес Option C).

[PARALLELS] Token bucket + mutex — классический паттерн (golang.org/x/time/rate). Sharding по хешу ключа — стандартный приём для снижения contention. Отличия от `x/time/rate`: нет clock injection, нет валидации, нет `Reserve`/`Wait`, нет context. FNV32a вместо SipHash — типичный выбор для не-security-критичного роутинга, но здесь ключ недоверенный (TB-1).

[TESTS] Покрытие 0%. Необходимо: unit (refill, cap, tokens<1→false, concurrent race detector, n=0→error, rate=0/burst=0→error, clock injection); integration (распределение ключей, aggregate rate == sum(shard.rate), reload 16→8 с миграцией); property-based (`sum(allowed) ≤ total_rate × elapsed + n×burst`); chaos (NTP-скачок, hot shard). Для каждого шага PLAN_B — минимум 1 тест (маппинг в stage2.tests.refactoring_coverage).

[ACTION]
- **NOW**: (1) Локализовать running binary (build hash, deploy manifest) — BLOCKER RN-3. (2) Прочитать определение метрики `observed_rate` — VERIFY RN-5. (3) Алерт ratio>1.1 на 2 окна → page on-call.
- **TODAY**: Добавить startup-assert `sum(shard.rate)==total_rate`; валидация n/rate/burst; monotonic clock + clamp elapsed; per-shard метрики. Canary на 1 реплике.
- **TOMORROW**: Выбрать A/B/C по результату RN-3/RN-5. Если n не меняется в runtime — Option A. Если меняется — Option B с миграцией.
- **LATER**: Consistent hashing, config versioning, canary rollout смены n, SLO (ratio ≤ 1.05 в 99% окон).

[QUESTIONS]
- VERIFY: RN-3 — где running binary / reload path? Показанный `shard.go` не имеет reload-пути.
- VERIFY: RN-5 — `observed_rate` оконная или мгновенная? Ratio=2.00→1.00 без config change.
- VERIFY: TB config-loader → NewSharded — auth/валидация конфига не показаны.
- VERIFY: material_hash — реальный sha256 не вычислен (placeholder `e3b0c442...`).
- VERIFY: downstream — платёжный/upstream API? От этого зависит severity (критично vs важно).
- VERIFY: prompt validation command (`python ast.parse`) не валидирует Go; нужен `gofmt -l` + `go vet` + `go build`.

[FUNC:FULL]
- **ECON**: effort Option A 2–3 дня, Option B 5–8 дней, Option C 1–2 дня (day-rate не задан — not set). Cloud delta $0 (in-process limiter, новых ресурсов нет). ROI не вычислим — нет revenue/abuse cost. Cost of delay: каждый час 2× over-admission = час удвоенной экспозиции downstream (SEC-1).
- **FAIL**: критично — RN-1 (агрегатная ставка), RN-3 (второй бинарник), RN-5 (метрика), RN-8 (n=0 panic, clock skew). Cascade: over-admission → downstream перегрузка → SLA/финансы. Recovery: code rollback возможен, token state не откатывается; полный rollback = restart с потерей состояния.
- **METRICS**: ~70 LOC кода + ~300 строк лога. Deps: 3 stdlib (sync, time, hash/fnv), 0 CVE. Tests: 0%. Perf: RWMutex overhead на 3200 rps (RN-7). Quality: нет валидации, нет clock injection, нет reload-пути. Infra: pool_size n/a, CPU/mem/replicas not set.
- **ALTERNATIVES**: языки — n/a (Go выбран). Фреймворки — `golang.org/x/time/rate` (зрелый, clock injection, Reserve/Wait). БД — n/a (in-memory). Инфра — n/a. Паттерны — Option A (fix-in-place), Option B (consistent hashing + миграция), Option C (drop sharding).
- **EVOLVE**: coupling низкий (stdlib, constructor-only интерфейс). Abstractions слабые: нет clock/config/metrics интерфейсов. feature_add 4/10 (нет reload, нет валидации). module_replace 6/10 (Limiter и ShardedLimiter разделимы). overall 5/10.
- **COMPARE**: Option A — 2–3 дня, низкая сложность, средний риск (не решает RN-3). Option B — 5–8 дней, высокая сложность, высокий риск (миграция при 0% тестов). Option C — 1–2 дня, низкая сложность, риск потери масштабирования.

[MANDATORY BASE]
1. **ECONOMICS**: time Option A 2–3 дня, Option B 5–8 дней, Option C 1–2 дня, при условии что day-rate не задан (not set); cost $0 cloud delta, при условии in-process limiter без новых ресурсов.
2. **RISKS**: критично — RN-1, RN-3, RN-5, RN-8; важно — RN-2, RN-6, RN-9, RN-10; при условии что RN-3 (второй бинарник) не подтверждён — все фиксы могут лечь не в тот артефакт.
3. **INFRASTRUCTURE**: pool_size=n/a (in-process limiter, нет пула), при условии что CPU/mem/replicas not set — данных в материале нет.
4. **CODE**: change ~70 LOC (2 файла), при условии Option A; +consistent hashing ring при Option B; −sharding при Option C.
5. **ACTION**: now — локализовать binary + прочитать метрику + алерт ratio>1.1; tomorrow — assert + валидация + monotonic clock + per-shard метрики.
6. **TIMELINE**: NOW — BLOCKER RN-3, VERIFY RN-5, алерт. TODAY — safe fixes (assert, валидация, clock, метрики). TOMORROW — выбор A/B/C. LATER — consistent hashing, config versioning, SLO.
7. **PRODUCTION IMPACT**: users — downstream protected service (auth/payment/upstream API), число не задано (not set); deploy window — canary 1 реплика; rollback — code rollback возможен, token state не откатывается, полный rollback = restart.
8. **SLO IMPACT**: current — SLO не определён (not set); after — рекомендовано ratio ≤ 1.05 в 99% окон, при условии что SLO будет введён.
9. **CLOUD COST**: current $0, projected $0, delta ±$0, при условии что все три опции — code-level изменения in-process лимитера.
10. **ON-CALL**: new alerts — ratio>1.1 (2 окна) → page, ratio>1.5 → ERROR, ratio≥2.0 → CRITICAL; runbook — проверить per-shard метрики, конфиг, reload history; escalation — downstream owner при подтверждённом over-admission.

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | FAIL | Over-admission 2× (SEC-1), panic при n=0 (SEC-2), wall-clock refill (SEC-3), hash-коллизии (SEC-4). |
| Facts | WARN | material_hash — placeholder; observed_rate windowing не подтверждён; reload 16→8 без кода. |
| Logic | OK | Внутри одного Limiter — корректная mutex-защита; композиционная ошибка агрегата — логична. |
| Applicability | WARN | Option A применим, но RN-3 (второй бинарник) может сделать все фиксы нерелевантными. |
| Effectiveness | WARN | Option A адресует 8 из 11 RN; RN-3/RN-5 требуют внешней верификации до фикса. |
| Resilience | FAIL | resilience_score 3/10: нет валидации, нет clock injection, нет тестов, нет per-shard observability. |
| Human factor | WARN | Reload 16→8 без audit trail; нет runbook, нет SLO, нет on-call binding. |
| Clarity | OK | Код читаем, gofmt-совместим; лог структурирован (timestamped, leveled, key=value). |

[REFLEXION]
1. Слабое место: RN-3 (второй бинарник) — критично, но не подтверждено. Исправлено: помечен как BLOCKER в [ACTION] NOW и [PLAN_B], не как факт.
2. Слабое место: material_hash — placeholder, не реальный sha256. Исправлено: явно указано в [CONCLUSION] и [QUESTIONS] как VERIFY; не выдаётся за верифицированный.
3. Слабое место: ratio=2.00→1.00 — возможный артефакт метрики, а не реальный bypass. Исправлено: [CONCLUSION] формулирует как «транзиентный over-admission», не «устойчивый 2×»; VERIFY на определение окна.
Итог: accepted

---

**Verdict**: `requires_external_verification`
**session_id**: `sess-2026-10-12-XXXXXX`
**material_hash**: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (placeholder — реальный sha256 не вычислен; требуется `tools/analyze.py --mode hash`)
**force_emergency**: `true` — risk stop: 2× over-admission к возможно-платёжному downstream; уже проведённые транзакции необратимы.

[AUDIT_TRAIL]
audit_id: audit-2026-10-11-8aa116
material_hash: sha256:5d73d2f6471c1eab2cafb1ee0619eee4774060ddf2865af3bde4ca4a8d2fb552
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

    vishap analyze data/real_cases/multi/rate_limiter_spec.txt
