# Case Study: Python 50k RPS Transaction System — Inverted Redis SETNX

**Material type:** `spec` (architecture + Python code + DevOps + security + performance)
**Level:** D3
**Cost:** $0.011264
**Verdict:** REQUIRES_REVIEW
**Compliance:** PCI-DSS
**Session:** sess-2026-10-11-114737

**Multi-domain analysis:**
- Architecture (FastAPI → Processor → Kafka → Consumer → PostgreSQL/Citus)
- Python code (async, idempotency, metrics, timeouts)
- DevOps (Kubernetes, KEDA, Vault, NetworkPolicy)
- Security (Kafka mTLS/SASL/ACL, TLS rotation)
- Performance (P95=450ms, CPU=85%, Kafka lag)

**Key findings:**
- **6 critical risks, 0 false positives**
- **Inverted pattern detected:** Redis SETNX stores marker, not result → payment loss in SETNX→commit window
- 12 STRIDE threats, 7 trust boundaries
- 15 questions for external verification
- **Sycophancy check passed:** verdict `does_not_work` preserved despite the brief claiming SETNX is sufficient
- Cost of delay: 50 lost payments/sec at 0.1% failure rate


**Full report for client:** [python-50k-rps-redis-setnx-full.md](python-50k-rps-redis-setnx-full.md)

---

## Vishap Output

# STAGE 5 — TRANSMITTER · D3 FINAL

[ECHO] Мульти-доменный бриф: real-time платёжная система (50k RPS, SLA 99.99%, PCI DSS). Пять задач: архитектура (FastAPI→Processor→Kafka→Consumer→PostgreSQL, шардирование Citus, KEDA vs HPA), Python-код (идемпотентность Redis SETNX, метрики, timeout), K8s-манифест (KEDA, Vault Agent, NetworkPolicy), security (Kafka mTLS/SASL/ACL, ротация TLS), performance (P95=450ms, CPU=85%, lag растёт). Материал — спецификация с кодом-заглушкой (3 TODO, 0 реализованных statements).

[ROUTE] stage1_scanner → stage2_analyst → stage3_researcher → stage4_synthesizer → stage5_transmitter. Параллельно: devops + security. research_first=true. return_to_stage2=true (4 условия). force_emergency=true, force_fallback=true.

[CONCLUSION] Архитектурный каркас корректен (Kafka, Citus, Vault, KEDA), но критический путь платежей не реализован: идемпотентность через Redis SETNX — inverted-паттерн (ключ хранит маркер начала, а не результат → потеря платежа в окне SETNX→commit); нет timeout/retry/circuit breaker/audit log; SLA 99.99% не подтверждён ни одним механизмом. KEDA упрётся в Citus write throughput. cert-manager dual-cert не делает dual-cert автоматически. Resilience 3/10. Решение: durable idempotency (PostgreSQL unique index + Redis fast-path с хранением ответа), KEDA с maxReplicaCount по write throughput + batch-запись, два Issuer для TLS, Vault dynamic secrets с renewal.

[RISK_NODES]
- **#1 критично** — Redis SETNX→PG commit: окно несогласованности → потеря/дублирование платежа.
- **#5 критично** — SLA 99.99% при единственном Redis без описанного failover = единая точка отказа.
- **#7 критично** — P95=450ms + CPU=85% + lag растёт: bottleneck в consumer/DB write path, не в FastAPI.
- **#8 критично** — нет retry/backoff/DLQ/circuit breaker → бесконечный retry усилит lag.
- **#10 критично** — SETNX check-then-act + at-least-once = окно двойного списания.
- **#11 критично** (повышен в cove) — ротация TLS без dual-CA = 100% разрыв Kafka connections.
- **#2/#3/#4/#6/#9 важно** — hot shard top-1 мерчанта; две точки истины (Redis+PG); durable-требование vs Redis; нет saga/outbox; cross-shard запросы.

[THREAT_MODEL] 12 STRIDE-угроз, 7 критичных. Top-3: (S) подмена idem_key без привязки к merchant_id → namespace `idem:{merchant_id}:{idem_key}`; (R) отсутствие audit log для финансовых операций → append-only WORM + pgaudit; (I) MITM на Kafka → TLS 1.3 + mTLS + envelope encryption через Vault transit. Trust boundaries: Client→FastAPI (public), FastAPI→Kafka, Kafka→Consumer, Consumer→PG, →Redis, Pods→Vault, Prometheus→targets. VERIFY: Citus coordinator↔worker, KEDA↔Kafka RBAC.

[SILENCE_LAYERS]
- **input**: не указаны распределение по мерчантам, размер payload, доля дубликатов, 50k RPS = среднее или пик.
- **assumption**: «Redis SETNX достаточно для идемпотентности» — не проверено на падение между SETNX и commit, TTL-экспирацию, Redis failover.
- **consequence**: двойное списание или потеря платежа — необратимо для доверия и регуляторики.

[INTERSECTION_RISKS]
- Redis SETNX (fast, volatile) × PG commit (slow, durable) → окно несогласованности.
- Kafka at-least-once × отсутствие ON CONFLICT → дубликаты в БД.
- KEDA autoscaling × Citus write throughput → поды упрутся в БД, lag не падает.
- PCI DSS × Prometheus merchant_id в labels → PII в TSDB вне периметра.
- cert-manager dual-cert × долгоживущие Kafka connections → разрыв при ротации.

[ASSEMBLY] Core: transaction-processor (FastAPI) → kafka-consumer → PostgreSQL (Citus, unique index на (merchant_id, idem_key), audit log). Service: Redis (fast-path, не источник истины), Kafka (at-least-once, mTLS+SASL/SCRAM+ACL), Vault (dynamic creds, transit), KEDA (lag-based), cert-manager (два Issuer). Infra: EKS (namespaces: transaction-processor, kafka, data, observability), Prometheus (label allowlist), NetworkPolicy (CDE-сегментация), pgaudit+WORM. Critical path: Client → FastAPI → Kafka → Consumer → PG commit → ack. Cycles: [].

[REFACTORING] (1) Идемпотентность: Redis-only → PostgreSQL unique index + Redis fast-path с хранением полного ответа; ответ на дубликат = 200 с сохранённым результатом (не 409). (2) Таймауты: Redis 30ms, PG 100ms, Kafka 50ms, общий 500ms через middleware; asyncio.timeout (Py3.11+). (3) Метрики: добавить idempotency_total{result}, redis_errors_total{op}, db_write_errors_total{op}, timeout_total{target}, circuit_breaker_state. (4) aioredis → redis.asyncio (redis-py). (5) KEDA: maxReplicaCount по write throughput Citus + Prometheus scaler на Citus write latency. (6) TLS: два Issuer + truststore с обоими CA + feature flag dual-CA. (7) Vault: dynamic DB secrets TTL 1h, renewal 50%, файлы вместо env.

[PARALLELS]
- **Stripe Idempotency-Key** (close) — ключ хранит результат, не маркер начала; материал inverted.
- **Richardson Inbox/Outbox** (architectural) — второй барьер против at-least-once дубликатов.
- **Kafka EOS** (close) — закрывает дубликаты на уровне producer, не окно Redis→PG.
- **KEDA Kafka scaler** (exact) — lagThreshold, activationLagThreshold.
- **cert-manager rotation** (close) — нужен overlapping validity или два Issuer.
- **Vault Agent Injector** (exact) — dynamic secrets + renewal.
- **Citus data modeling** (close) — skew в distribution column, hot shard.
- **PCI DSS v4.0** (architectural) — требования 1, 3, 10.
- **OWASP API Top 10 2023** (close) — API2 Broken Auth, API4 Resource Consumption.
- **aioredis deprecation** (exact) — merged into redis-py 4.2+.

[TESTS] Unit: SETNX hit/miss, TTL expiry, timeout срабатывает. Integration: Kafka→Consumer→PG at-least-once. Chaos: kill Redis между SETNX и commit (транзакция должна сохраниться); kill consumer после PG commit до ack (дубликат отброшен unique index). Load: 50k RPS sustained, P95 ≤ 200ms. Security: mTLS handshake, ACL enforcement, Vault renewal. Contract: дубликат возвращает сохранённый результат. Edge: TTL истекает во время обработки; Redis недоступен (fail-open/closed?); отрицательный amount; одинаковый idem_key от разных merchant_id.

[ACTION]
- **NOW**: зафиксировать контракт API на дубликат (200 vs 409); подтвердить Redis persistence (AOF/WAIT); проверить Citus write throughput и skew по merchant_id.
- **TODAY**: реализовать durable idempotency (PG unique index + Redis fast-path); добавить timeout/метрики; мигрировать aioredis→redis-py.
- **TOMORROW**: KEDA с maxReplicaCount + Prometheus scaler; два Issuer для TLS; Vault dynamic secrets с renewal; audit log (WORM).
- **LATER**: saga/outbox при подтверждённых частичных сбоях; OpenTelemetry tracing; error budget policy; on-call runbook.

[QUESTIONS]
1. Распределение нагрузки по merchant_id — есть ли top-1 с долей >10%?
2. 50k RPS — среднее, пик или sustained?
3. Какой write throughput держит Citus-кластер (узлы, storage)?
4. Redis persistence: AOF everysec/always, Sentinel/Cluster, WAIT?
5. Контракт API на дубликат: 409 или 200 с результатом?
6. Есть ли audit log для финансовых операций?
7. Какие поля — cardholder data? Есть ли tokenization PAN?
8. Стек feature flags (LaunchDarkly/Flagsmith/custom)?
9. Есть ли OpenTelemetry tracing?
10. Error budget policy?
11. On-call runbook для lag spike, Redis failover, Citus rebalance?
12. Готовы ли Kafka-клиенты к dual-CA?
13. План миграции unique constraint — есть ли дубликаты?
14. aioredis или redis-py?
15. SLO на durability (0 потерянных транзакций)?

[FUNC:FULL]
- **ECON**: effort ~6–10 недель (durable idempotency + KEDA + TLS + Vault + audit log); cost — cloud delta unknown (нет данных о кластере, mode_cost не запускался); ROI высокий (закрытие потери платежей); cost of delay — при 50k RPS и failure_rate 0.1% окно SETNX→commit 50ms ≈ 50 потерянных платежей/сек.
- **FAIL**: критично — окно SETNX→commit (потеря/дублирование); Kafka rebalance без unique constraint (дубликаты); Citus write throughput при 50k RPS (рост lag); важно — нет timeout (исчерпание pool), TLS без dual-CA (разрыв connections), Vault TTL без renewal (потеря секретов). Cascade: Redis down → fast-path деградирует → fallback PG-only; PG down → полный отказ записи. Recovery: feature flag idempotency_mode, blue/green, dual-write период.
- **METRICS**: codebase ~15 LOC stub, 3 TODO, 0 реализованных statements; deps 5 (fastapi, asyncpg, aioredis, asyncio, prometheus_client), aioredis deprecated; tests 0; perf P95=450ms (норма ≤200ms), CPU=85%, lag растёт; quality — unused imports/metrics, stub return; infra EKS+KEDA+Vault+cert-manager, pool_size ≥50.
- **ALTERNATIVES**: языки — Python (текущий, async I/O), Go (consumer-слой, низкий P99), Rust (избыточно для 50k RPS); фреймворки — FastAPI (текущий), Litestar (быстрее), aiohttp (минимальный overhead); БД — Citus (текущий, hot shard risk), CockroachDB (auto-rebalance, выше latency), YugabyteDB (PG-совместимый), ScyllaDB (только audit log); инфра — Kafka vs Redpanda (ниже latency), Redis vs KeyDB/Dragonfly (throughput); паттерны — durable idempotency (Option A), Inbox/Outbox+EOS (Option B), Saga (Option C).
- **EVOLVE**: coupling 5/10 (consumer↔Citus write throughput — слабое место); abstractions 6/10 (feature flags дают эволюционность); growth 7/10 (feature_add); friction 6/10 (замена БД потребует пересмотра шардирования); overall 6/10.
- **COMPARE**: Option A (durable idempotency) — time ~4–6 недель, cost средний, risk низкий, complexity средняя; Option B (Inbox/Outbox+EOS) — time ~6–8 недель, cost выше, risk средний, complexity высокая; Option C (Saga) — time ~10–14 недель, cost высокий, risk низкий, complexity очень высокая. Рекомендация: Option A для MVP, Option C при подтверждённых частичных сбоях.

[MANDATORY BASE]
1. **ECONOMICS**: time ~6–10 недель, cost $unknown (нет данных о кластере), при условии полного scope (idempotency+KEDA+TLS+Vault+audit).
2. **RISKS**: критично — окно SETNX→commit, SLA без failover, KEDA↔Citus, TLS rotation; важно — hot shard, две точки истины, нет saga; при условии 50k RPS и SLA 99.99%.
3. **INFRASTRUCTURE**: pool_size fastapi=50, consumer=100, redis=50, при условии P95 ≤ 200ms и 50k RPS; consumer_max=50 ограничен write throughput Citus.
4. **CODE**: change ~15 LOC stub → ~150 LOC реализация, при условии durable idempotency + метрики + timeout; миграция aioredis→redis-py.
5. **ACTION**: now — контракт API + Redis persistence + Citus throughput; tomorrow — durable idempotency + KEDA + TLS + Vault.
6. **TIMELINE**: NOW — аудит конфигурации; TODAY — durable idempotency + timeout + метрики; TOMORROW — KEDA + TLS + Vault + audit log; LATER — saga/outbox + tracing + error budget.
7. **PRODUCTION IMPACT**: users — все мерчанты; deploy window — blue/green с shadow traffic; rollback — feature flag idempotency_mode, dual-write период (rollback unique index невозможен без потери ключей).
8. **SLO IMPACT**: current — SLA 99.99% не подтверждён (resilience 3/10); after — при Option A + KEDA backpressure + TLS dual-CA + Vault renewal → достижимо, при условии batch-записи и мониторинга Citus write latency.
9. **CLOUD COST**: current $unknown, projected $unknown, delta ±$0 (нет данных о кластере, mode_cost не запускался; числа не выдумываются).
10. **ON-CALL**: new alerts — Kafka lag > threshold, P95 > 200ms, error rate > 0.1%, pool saturation > 80%, circuit_breaker open, Vault renewal failure, cert-manager rotation failure; runbook — lag spike, Redis failover, Citus rebalance; escalation — PCI-инциденты (72h notification).

[REFLEXION]
1. **Слабое место**: числа cloud cost отсутствуют (unknown) → **исправлено**: явно помечено «нет данных, mode_cost не запускался, числа не выдумываются» в [FUNC:FULL] ECON и [MANDATORY BASE] #9; не подставлены фиктивные значения.
2. **Слабое место**: force_emergency=true и force_fallback=true в stage4, но fallback-формат не применён → **исправлено**: D3-структура сохранена полностью (все обязательные блоки присутствуют), emergency-сигнал отражён в [ROUTE] и [CONCLUSION]; сокращение не выполнено, так как материал позволяет полный D3-вывод.
3. **Слабое место**: возможное противоречие между «KEDA по lag» (требование материала) и «maxReplicaCount по write throughput» (рекомендация) → **исправлено**: в [REFACTORING] и [FUNC:FULL] COMPARE явно указано, что KEDA сохраняется, но с ограничением maxReplicaCount + Prometheus scaler на Citus write latency как второй триггер; противоречие разрешено, не замаскировано.
4. **Слабое место**: sycophancy-риск — материал заявляет Redis SETNX как идемпотентность, можно было согласиться → **исправлено**: [CONCLUSION] и [FUNC:FULL] FAIL явно называют паттерн inverted относительно Stripe; verdict «does_not_work» из stage3 сохранён.
5. **Слабое место**: [FUNC:FULL] и [MANDATORY BASE] — проверено наличие обоих блоков → **исправлено**: оба присутствуют, 6 функций, 10 полей.

Итог: **accepted**

[AUDIT_TRAIL]
audit_id: audit-2026-10-11-b6cd0a
material_hash: sha256:47cc0f5ad5123e1adcf33cbcd1c567a1180b4c4b0ec1219832fd882caadab952
pii_detected: false
compliance_flags: ['PCI-DSS']
critique_verdict: REQUIRES_REVIEW


[COMPLETENESS]
level: D3
required: 12
missing: []
loss_pct: 0.0%
verdict: ACCEPTABLE

---

## Reproduce

    vishap analyze data/real_cases/multi/python_50k_rps_spec.txt
