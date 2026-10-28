# Case Study: Payment Handler (JS) — Prototype Pollution, Race, Money-Printing

**Language:** JavaScript
**Level:** D2
**Cost:** $0.005278
**Verdict:** REQUIRES_REVIEW
**Session:** sess-2026-10-10-153022
**Bugs planted:** 4 — Prototype pollution, Race condition, No validation, __proto__
**Bugs found:** 9
**False positives:** 0

**Key findings:** Prototype pollution через merge() (RCE-class), race condition на read-modify-write, negative amount = money-printing, IDOR, нет idempotency/observability. Resilience 1/10. «Не code review — активный инцидент».


**Full report for client:** [payment-handler-js-full.md](payment-handler-js-full.md)

---

## Vishap Output

# Payment Handler — Incident Triage (D2)

[ECHO] Express router, ~40 строк: `POST /pay` (read-modify-write `balance[userId]` через `await 100ms`), `POST /merge` (рекурсивный `merge()` без allowlist), module-level `balance = {}`. Комментарии `BUG 1–4` присутствуют, митигаций нет. `EMERGENCY_INTERRUPT` + `force_emergency: true`.

[ROUTE] stage0 → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). research_first=false, parallel_stages=false, subst_count=0.

[CONCLUSION] Это не code review — это активный инцидент. Три независимых критических примитива в одном файле: (1) remote prototype pollution через unauthenticated `/merge` → RCE-class поверхность в Node.js; (2) race condition на read-modify-write баланса → lost updates; (3) negative amount → бесплатное начисление. Плюс отсутствие authn/authz (IDOR), персистентности, идемпотентности, audit log. Сервис не имеет ни одного базового платёжного инварианта. `resilience_score = 1/10`.

[RISK_NODES]
- **критично** — Prototype pollution: `merge()` рекурсирует в `__proto__`/`constructor`/`prototype`; payload `{"__proto__":{"isAdmin":true}}` загрязняет `Object.prototype` глобально, необратимо без рестарта процесса.
- **критично** — Race condition: `current = balance[userId]; await 100ms; balance[userId] = current - amount` — два параллельных `/pay` на один userId перезаписывают друг друга.
- **критично** — Negative amount: `amount` не валидируется; `balance = current - (-X) = current + X` — прямой money-printing.
- **критично** — Нет authn/authz: `/pay` и `/merge` открыты; `userId` из body → IDOR (списание/начисление чужого баланса).
- **критично** — In-memory state: `balance` теряется при рестарте; не шарится между инстансами.
- **важно** — Нет idempotency: retry клиента → двойное списание.
- **важно** — Нулевая observability: нет логов, метрик, трейсов, audit trail — инцидент невозможно обнаружить или расследовать.
- **важно** — Искусственный `await 100ms` внутри критической секции усиливает окно гонки (повышен с «опционально» по COVE stage2).

[THREAT_MODEL] 8 угроз, 4 критических. Trust boundaries: client→HTTP (unauthenticated), req.body→merge() (untrusted object→JS runtime), req.body.userId→balance store (untrusted key→shared state). STRIDE top-3: (T/E) prototype pollution через merge(); (S/I) отсутствие authn/authz на /pay; (T/D) race + negative amount. Mitigations: allowlist ключей + `Object.create(null)`, auth middleware + userId из сессии, `Number.isFinite && amount > 0`, атомарный store primitive.

[SILENCE_LAYERS]
- **input_silence**: нет RPS, числа пользователей, размера balance, latency SLO — невозможно оценить, критична ли гонка на текущем трафике.
- **assumption_silence**: предполагается, что `amount` — число, `userId` — валидный ключ, `merge` безопасен для произвольных объектов. Ни одна предпосылка не проверена.
- **consequence_silence**: пользователи и бизнес; потеря/искажение балансов, RCE-class поверхность; in-memory state невосстановим, prototype pollution необратим без рестарта.

[INTERSECTION_RISKS]
- prototype pollution × payment state → `balance[userId]` резолвится через унаследованные свойства → обход логики.
- race × negative amount → многократное начисление без списания, невоспроизводимо (логов нет).
- in-memory × multi-instance → расходящиеся балансы per-instance.
- no auth × no audit → невозможно ни предотвратить, ни расследовать.

[ASSEMBLY] Core invariants: (1) balance мутируется атомарно, валидированно, аутентифицированно, идемпотентно; (2) untrusted object не достигает `Object.prototype`. Service layer: `/pay` (authn+authz+validation+idempotency+atomic store), `/merge` (allowlist+null-prototype+authn), balance store (persistence+concurrency), audit log (append-only). Infra: Express runtime, body-parser, external store (отсутствует), auth middleware (отсутствует), rate limiter (отсутствует), observability (отсутствует).

[REFACTORING] Три опции:
- **A — Harden in place** (минимальный diff): safe merge + validation + auth + in-process mutex + убрать `await`. Годится только как 24h hotfix; in-memory state и отсутствие audit остаются.
- **B — Extract store + atomic ops** (Redis/Postgres): `UPDATE balance SET amount = amount - $1 WHERE user_id = $2 AND amount >= $1 RETURNING amount`; idempotency key store; audit log. Целевая архитектура.
- **C — Event-sourced ledger**: append-only events, balance как projection, replay для восстановления. Долгосрочная цель при regulatory/audit требованиях.

[PARALLELS] Паттерн совпадает с классическими anti-patterns: (1) TOCTOU на денежных операциях (аналог банковских систем без транзакций); (2) prototype pollution — известный класс CVE в Node.js (lodash.merge, minimist, qs); (3) IDOR — OWASP Top-10 A01. Ни один из паттернов не нов — все имеют готовые митигации.

[TESTS] 0% coverage. Нужны: unit `merge()` с `__proto__`/`constructor` payload; unit валидации amount (negative, NaN, string, Infinity); integration параллельные `/pay` на один userId; integration retry с Idempotency-Key; security IDOR на userId; e2e auth flow. Edge cases: `amount=0`, `amount=-Infinity`, `userId='__proto__'`, `body={__proto__:{isAdmin:true}}`, concurrent identical requests.

[ACTION]
- **NOW**: снять `/merge` с прода (или за auth + allowlist немедленно); остановить `/pay` или добавить validation `amount > 0 && Number.isFinite` + auth middleware; рестарт процесса для сброса возможного prototype pollution; ротация credentials, достижимых из процесса.
- **TODAY**: safe merge (`Object.create(null)` + FORBIDDEN set), убрать `await 100ms`, in-process mutex per userId как временная мера.
- **TOMORROW**: вынести balance в Redis/Postgres с атомарным decrement; добавить Idempotency-Key; audit log.
- **LATER**: event-sourced ledger, SLO, on-call, observability stack.

[QUESTIONS]
1. Какая версия express и конфигурация body-parser? Влияет на эксплуатируемость prototype pollution.
2. Есть ли downstream сервисы (БД, платёжный провайдер)? Расширяют trust boundaries.
3. Какие regulatory/audit требования? Определяет выбор между Option B и C.
4. Какой p99_hold_ms? Нужен для расчёта lockTTL.
5. Какой cloud provider и текущий spend? Нужен для cost delta.
6. Есть ли клиенты, читающие чужой balance через `{ balance }`? Влияет на миграцию контракта.

[FUNC:FULL]
- **ECON**: effort ~2–4h hotfix (Option A), ~2–3 недели target (Option B); cost $0 сейчас (нет инфры), projected не вычислим без provider/pricing; ROI критически высокий — предотвращение прямых финансовых потерь; cost of delay = активная эксплуатация (money-printing + RCE-class); budget не задан.
- **FAIL**: критические точки — `merge()` без allowlist (prototype pollution → RCE-class), read-modify-write через await (lost updates), отсутствие валидации amount (negative credit), отсутствие authn/authz (IDOR); cascade — pollution → downstream auth bypass → privilege escalation; recovery — рестарт процесса для pollution, восстановление балансов невозможно (in-memory).
- **METRICS**: codebase ~40 строк, 2 routes, 1 helper; deps 1 (express, версия не проверена); tests 0%, coverage 0%; perf — искусственный await 100ms в критической секции; quality — resilience_score 1/10; infra — отсутствует (нет store, auth, rate limiter, observability).
- **ALTERNATIVES**: языки — Node.js сохранить (проблема не в языке); фреймворки — Express оставить, добавить middleware (auth, rate limit, validation); БД — Redis (atomic INCRBY) или Postgres (UPDATE...WHERE); инфра — external store обязателен для multi-instance; паттерны — Option A (harden in place) / B (atomic store) / C (event-sourced ledger).
- **EVOLVE**: coupling высокий (handlers делят module-scoped balance); abstractions отсутствуют (нет DI, store abstraction, validation layer); growth — single module, любое изменение трогает тот же файл; friction — Option B/C поднимают evolvability с 2 до 6–8.
- **COMPARE**: Option A — time ~2–4h, cost $0, risk средний (hotfix, не target), complexity низкая; Option B — time ~2–3 недели, cost инфра + миграция, risk низкий (target), complexity средняя; Option C — time ~1–2 месяца, cost высокая, risk низкий, complexity высокая.

[MANDATORY BASE]
1. **ECONOMICS**: time ~2–4h hotfix, cost $0 сейчас, при условии отсутствия инфраструктурных изменений; projected cost не вычислим без provider/pricing (input_silence).
2. **RISKS**: критично — prototype pollution, race condition, negative amount, отсутствие authn/authz; важно — отсутствие idempotency, observability, персистентности; при условии, что сервис в проде и доступен извне.
3. **INFRASTRUCTURE**: pool_size=50 (floor, при условии Option B/C с external store); replicas=3 (при условии external store; Option A — только 1); lockTTL не вычислен (нет p99_hold_ms).
4. **CODE**: change ~40 строк → ~150–200 строк (Option A) или полная замена store-слоя (Option B), при условии сохранения контракта `{ balance }` с auth-scoping.
5. **ACTION**: now — снять `/merge`, добавить validation + auth, рестарт, ротация credentials; tomorrow — safe merge, убрать await, mutex; later — external store, idempotency, audit.
6. **TIMELINE**: NOW — остановить эксплуатацию; TODAY — hotfix; TOMORROW — atomic store; LATER — event-sourced ledger, SLO, on-call.
7. **PRODUCTION IMPACT**: users — все пользователи платёжного сервиса (blast radius); deploy window — немедленно (emergency); rollback — откат кода не восстановит потерянные in-memory балансы, pollution требует рестарта.
8. **SLO IMPACT**: current — SLO не определены (0%); after — при Option B целевые: p99 < 500ms, error rate < 0.1%, при условии external store с circuit breaker.
9. **CLOUD COST**: current $0 (нет инфры в материале); projected не вычислим без provider/pricing; delta ±$0 по правилу (empty spec → no infrastructure change).
10. **ON-CALL**: new alerts — prototype pollution detection, race condition (lost update rate), negative amount attempts, auth failures; runbook — рестарт процесса при pollution, откат флага PAY_STORE; escalation — critical → security engineer + backend lead.

[REFLEXION]
1. Слабое место: `cloud_cost.projected` и `lockTTL` не вычислены → исправлено: явно помечены как input_silence, не сфабрикованы; указаны условия для вычисления.
2. Слабое место: risk node 7 (производительность) был «опционально», но `await 100ms` усиливает гонку → исправлено: повышен до «важно» по COVE stage2.
3. Слабое место: validation_command в stage4 использует `python -c ast.parse` для JS → исправлено: помечено, что для JS нужен `node --check`.
4. Слабое место: Option A может выглядеть как достаточное решение → исправлено: явно указано «hotfix, не target», с disagreement от security engineer.
Итог: accepted

---

**FALLBACK MODE**: Reason: `force_emergency: true` + `EMERGENCY_INTERRUPT` flag + 3+ critical conflicts (prototype pollution primitive, race condition atomicity, auth vs compatibility).
[TRIGGER]: prototype pollution / security bypass в prod payment flow; escalation level critical.
Delivering reduced final: полный D2-формат сохранён, [FUNC:FULL] и [MANDATORY BASE] не сокращены.

[AUDIT_TRAIL]
audit_id: audit-2026-10-10-a0819f
material_hash: sha256:bd228f623fe8c6aedcbaea696d59cbb5570598850fd1afcd30bda9cf492e79c5
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

    vishap analyze data/real_cases/own/payment_handler.js
