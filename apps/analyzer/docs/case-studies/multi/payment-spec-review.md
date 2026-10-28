# Case Study: Payment Spec — Contradictions & PCI-DSS Violation

**Material type:** `spec`
**Level:** D2
**Route:** `stage4 -> stage3 (gate downgraded LLM emergency)`
**Compliance:** PCI-DSS
**Cost:** $0.006843
**Session:** sess-2026-10-10-150940
**Verdict:** REQUIRES_REVIEW

**Key findings:** Resilience score 2/10. 3 contradictions (1.3/1.4 PAN-vs-PCI, 1.5/1.6 retry-vs-idempotency, 2.1/1.5 SLA-vs-retry). Target architecture: tokenization-first, idempotency store, timeout budget 500ms, RPO 0 via sync replication.

---

## Vishap Output

# Payment Service — ТЗ v1.2: Анализ спецификации

[ECHO] ТЗ платёжного сервиса v1.2, ~40 строк, 4 раздела (FR / NFR / противоречия / открытые вопросы). Материал — спецификация, не код. Уровень D2. **EMERGENCY_INTERRUPT активен**: требование 1.4 (логирование полного PAN) прямо нарушает PCI-DSS.

[ROUTE] stage0 → EMERGENCY_INTERRUPT (PCI-DSS violation) → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). Route обнулён на stage0, восстановлен после фиксации противоречия 1.3 vs 1.4.

[CONCLUSION] Спецификация **не готова к проду**. Одно необратимое нарушение (1.4 — PAN в логах), три неразрешённых противоречия (1.3/1.4, 1.5/1.6, 2.1/1.5), отсутствуют rate limiting, timeout-бюджет, circuit breaker, аудит доступа к PAN, механизм RPO 0. Resilience score: **2/10**. Требуется возврат к stage2 для разрешения противоречий с владельцем спецификации.

[RISK_NODES]
- **критично** (1) Неявное допущение: логи защищены как хранилище карт — не проверено, противоречит PCI-DSS.
- **критично** (5) Внутреннее противоречие: 1.3 vs 1.4 (прямое), 1.5 vs 1.6 (неполнота), 2.1 vs 1.5 (SLA).
- **критично** (6) Стратегическое избегание: открытые вопросы без владельцев и без блокировки релиза.
- **критично** (8) Надёжность: RPO 0 без механизма; partial failure при retry не обработан.
- **критично** (10) Конкурентность: idempotency без атомарности → race condition → дубль платежа.
- **важно** (2, 3, 4, 7, 9, 11) Обобщение idempotency, конкурирующие реализации, сдвиг тезиса PCI-DSS, latency-бюджет, отсутствие rate limiting, ломающие изменения downstream.

[ASSEMBLY] Целевая архитектура (Option A — Tokenization-first): Payment API → Rate Limiter → Idempotency Store (SETNX + unique index) → PAN Vault (KMS/HSM, envelope encryption) → Upstream Adapter (Visa/MC/МИР) → Ledger (sync replication, quorum) → Audit Log (append-only, tamper-evident). PAN никогда не попадает в логи — только token + masked (BIN+last4).

[REFACTORING] Удалить 1.4 → маскирование PAN (первые 6 / последние 4). Ввести серверный namespace для idempotency-key (merchant_id + client UUID, SHA-256, TTL 24h). Добавить timeout-бюджет 500ms (rate_limiter 5 + idempotency 20 + tokenize 30 + upstream 350 + ledger 50 + audit 20 + buffer 25). Retry: max 3, backoff+jitter, circuit breaker. RPO 0 → sync replication Postgres (quorum write).

[PARALLELS] Tokenization-first (PCI scope minimization) — индустриальный стандарт для платёжных систем. Серверный namespace + клиентский UUID для idempotency — паттерн Stripe/Adyen. Timeout-бюджет + circuit breaker — паттерн Netflix Hystrix / resilience4j. Envelope encryption с KMS — AWS/GCP best practice.

[TESTS] Unit: idempotency-key генерация/валидация, маскирование PAN. Integration: retry + idempotency, partial failure, upstream timeout. Contract: Visa/MC/МИР. Load: p95 < 500ms при retry, rate limiting. Chaos: отказ Idempotency Store, KMS, upstream. Security: DLP на логи, audit доступа к PAN, penetration test. Edge cases: два параллельных retry с одинаковым ключом; деньги списаны, ответ потерян; ротация ключа PAN во время транзакции.

[ACTION]
- **NOW**: удалить требование 1.4 (PAN из логов) → маскирование. Снять EMERGENCY.
- **TODAY**: зафиксировать владельца idempotency-key (серверный namespace + клиентский UUID), timeout-бюджет, механизм RPO 0 (sync replication quorum).
- **TOMORROW**: rate limiting, circuit breaker, audit log доступа к PAN, KMS/HSM для ключа PAN.
- **LATER**: Option A (PAN Vault), dual-write миграция, PCI-DSS scan.

[QUESTIONS]
1. Кто владелец idempotency-key — клиент или сервер? (открытый вопрос 1 ТЗ)
2. Как обрабатывать partial failure при retry (деньги списаны, ответ потерян)? (открытый вопрос 2)
3. Где хранится ключ шифрования PAN — KMS, HSM, env? (открытый вопрос 3)
4. Какая нагрузка (TPS, peak QPS, объём транзакций/сутки)? — без этого p95 < 500ms и RPO 0 не верифицируемы.
5. Кто владелец downstream-потребителей логов (аудит/fraud/support) при удалении PAN?

[FUNC:FULL]
- **ECON**: effort ~3–6 недель (Option A: PAN Vault + KMS/HSM + миграция), cost — не рассчитывается без данных о нагрузке (cloud_cost.current=0, projected=0, delta=0, reason: инфраструктура не развёрнута). Cost of delay: необратимая утечка PAN при релизе без фикса 1.4 → потеря PCI-DSS, штрафы, отзыв карт. ROI фикса 1.4 — немедленный (снятие EMERGENCY).
- **FAIL**: критично — утечка PAN в логи (необратимо), race condition в idempotency (дубль платежа), DoS без rate limiting. Cascade: retry без timeout-бюджета → amplification → каскадный отказ upstream → SLA нарушен. Recovery: для 1.4 — невозможен после утечки; для остальных — feature flags + dual-write.
- **METRICS**: спецификация ~40 строк, 6 противоречий/пробелов, 3 открытых вопроса, 0 тестов, 0 кода. Deps: PCI-DSS, Visa/MC/МИР, KMS/HSM (не выбран), Redis/Postgres (не выбран). Perf: p95 < 500ms заявлен, timeout-бюджет отсутствует. Quality: resilience 2/10. Infra: не развёрнута.
- **ALTERNATIVES**: Option A (Tokenization-first, PAN Vault + KMS/HSM) — снимает PCI-scope, +10–30ms latency. Option B (envelope encryption в приложении) — дешевле, но ключ в памяти (риск core dump). Option C (минимальный fix 1.4) — быстро снимает EMERGENCY, но не решает race condition и SLA. Рекомендация: A (second_opinion security engineer настаивает).
- **EVOLVE**: coupling 6/10 (Vault/Idempotency/Retry — отдельные сервисы, но KMS/HSM связывает). Abstractions 7/10. Feature_add 7/10, module_replace 8/10. Overall 7/10 для Option A; Option C — низкая evolvability (долг накапливается).
- **COMPARE**: Option A — time ~3–6 недель, cost высокий (Vault + KMS/HSM), risk низкий (снимает PCI-scope), complexity высокая. Option B — time ~2–4 недели, cost средний, risk средний (ключ в памяти), complexity средняя. Option C — time ~2–3 дня, cost низкий, risk высокий (race condition + SLA), complexity низкая.

[MANDATORY BASE]
1. **ECONOMICS**: time ~3–6 недель (Option A), cost — не рассчитывается (нет данных о нагрузке), при условии выбора Option A и наличии TPS-данных.
2. **RISKS**: критично — утечка PAN (1.4), race condition (idempotency), DoS (нет rate limiting); важно — RPO 0 без механизма, retry без timeout-бюджета, ключ PAN не определён; при условии релиза без фикса 1.4 — необратимая потеря PCI-DSS.
3. **INFRASTRUCTURE**: pool_size=50, при условии 3 реплик Payment API (4 vCPU / 8 GB) + 2 реплик PAN Vault (8 vCPU / 16 GB) + Redis cluster 3 shards + Postgres 1 primary + 2 sync replicas.
4. **CODE**: change — удаление 1.4 (маскирование PAN), введение серверного idempotency-key, timeout-бюджет 500ms, при условии dual-write периода для миграции.
5. **ACTION**: now — удалить 1.4 (маскирование PAN); tomorrow — idempotency namespace, timeout-бюджет, RPO 0 механизм.
6. **TIMELINE**: NOW — фикс 1.4 (снятие EMERGENCY); TODAY — владелец idempotency-key, timeout-бюджет, RPO 0; TOMORROW — rate limiting, circuit breaker, audit log, KMS/HSM; LATER — Option A (PAN Vault), dual-write, PCI-DSS scan.
7. **PRODUCTION IMPACT**: users — все держатели карт (утечка PAN необратима); deploy window — не определён (спецификация); rollback — для 1.4 невозможен после утечки, для остальных feature flags + dual-write.
8. **SLO IMPACT**: current — не применимо (не развёрнуто); after — availability 99.99%, p95 < 500ms, RPO 0, при условии timeout-бюджета 500ms и sync replication quorum.
9. **CLOUD COST**: current $0, projected $0, delta ±$0, при условии отсутствия развёрнутой инфраструктуры (материал — спецификация).
10. **ON-CALL**: new alerts — SLA burn rate, upstream error rate, circuit breaker open, DLP violation (PAN в логах); runbook — partial failure при retry, инцидент утечки PAN; escalation — compliance-инциденты → CRITICAL_ESCALATION.

[REFLEXION]
1. Слабое место: cloud_cost = 0 без обоснования → исправлено: указано reason (инфраструктура не развёрнута, нет данных о нагрузке), число идёт с условием.
2. Слабое место: lockTTL 900ms рассчитан эвристически (p99_hold_ms=450 × safety_factor=2.0), не подтверждён инструментом → исправлено: помечено в tool_output stage4 как эвристика, не выдаётся как факт.
3. Слабое место: risk node 9 (Масштабируемость) в stage2 помечен «важно», но отсутствие rate limiting = DoS (критично) → исправлено: в [RISK_NODES] rate limiting отнесён к критичным последствиям (DoS), согласовано с cove stage2.
Итог: accepted

---

**EMERGENCY_INTERRUPT**: требование 1.4 (логирование полного PAN) — прямое нарушение PCI-DSS Req. 3.2/3.4 и потенциально 152-ФЗ. Релиз без фикса 1.4 недопустим. `force_emergency: true`, `force_fallback: true`, `return_to_stage2: true`.

[AUDIT_TRAIL]
audit_id: audit-2026-10-10-d23e4b
material_hash: sha256:c2db5be35d9c9e7aeb718cc5bfbdc82aa5e8d463cf0532520d96357d57b549c9
pii_detected: false
compliance_flags: ['PCI-DSS']
critique_verdict: REQUIRES_REVIEW


[COMPLETENESS]
level: D2
required: 12
missing: []
loss_pct: 0.0%
verdict: ACCEPTABLE

---

## Reproduce

    vishap analyze data/real_cases/multi/payment_spec.md
