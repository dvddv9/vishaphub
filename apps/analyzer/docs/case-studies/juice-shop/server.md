# Case Study: OWASP Juice Shop — server.ts

**Source:** `server.ts`
**Language:** TypeScript
**Level:** D3
**Cost:** $0.007754
**Verdict:** REQUIRES_REVIEW
**Session:** sess-2026-10-10-192207

---

## Vishap Output

# OWASP Juice Shop — server.ts: анализ bootstrap-файла

[ECHO] Материал: `server.ts` (OWASP Juice Shop, TypeScript, Express bootstrap). Уровень D3. Slice: импорты + middleware-регистрация + startup-оркестрация. Route-регистрация и error-handler вне slice. `subst_count=0`, `research_first=false`, stage3 отсутствует. Флаги: `REJECT_TOO_LARGE`, `VERIFY` (output/decider/cost/irreversibility не заданы автором).

[ROUTE] stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). Stage3 пропущен (research_first=false). Stage4 вернул `return_to_stage2=true`, `force_emergency=true` — 2 критичных конфликта Analyst↔Synthesizer.

[CONCLUSION] `server.ts` — god-file: 60+ импортов, ~25 middleware-регистраций, startup-оркестрация и config-загрузка в одном модуле. Три критичных дефекта: (1) startup-задачи запускаются fire-and-forget без `await` — сервер принимает трафик до готовности; (2) `app.locals` хранит security-флаги (`abused_ssti_bug`, `abused_ssrf_bug`) как shared mutable state — cross-request влияние и рассинхрон при multi-instance; (3) wildcard CORS (`app.use(cors())`) применяется глобально ко всем маршрутам, включая аутентифицированные. Часть ослаблений намеренна (учебный проект Juice Shop), но в production-контексте — критично. `resilience_score=4/10`.

[RISK_NODES]
- **критично** — Startup без `await` (risk_node #1, #8): `validateConfig` может упасть, сервер всё равно стартует.
- **критично** — `app.locals.abused_ssti_bug` / `abused_ssrf_bug` — глобальные флаги, разделяемые между запросами (risk_node #10).
- **критично** — Wildcard CORS на всех маршрутах (SEC-1, risk_node #2).
- **критично** — Отключён `helmet.xssFilter()` с комментарием-признанием (SEC-2, risk_node #5).
- **важно** — `require()` в ESM-модуле (SEC-4, risk_node #3).
- **важно** — Monkey-patch `res.end` в `serveIndexMiddleware` (SEC-3, risk_node #11).
- **важно** — `app.locals.captchaId` / `captchaReqId` — in-process state, рассинхрон при масштабировании (risk_node #9).
- **важно** — `compression()` на `/metrics` — потеря scrape-данных (risk_node #7, повышен с «опционально»).
- **важно** — Отсутствие timeout / circuit breaker / idempotency (contracts).
- **опционально** — Секреты: в slice не найдены, но `config.get()` читает из внешнего источника — не проверено.

[THREAT_MODEL] 7 trust boundaries (TB1–TB7), из них TB6 (websocket) и TB7 (внешние payment/web3/delivery) не разобраны — код вне slice. 12 угроз: 6 критичных, 5 важных, 1 опциональная. Top-3: (1) TB1-S wildcard CORS; (2) TB3-T SQLi через finale-rest auto-endpoints; (3) TB4-I path traversal в file servers (`servePublicFiles`, `serveLogFiles`, `serveQuarantineFiles`, `serveKeyFiles`).

[SILENCE_LAYERS]
- **Input silence**: нет RPS, размера БД, числа пользователей, размера статики → SLO и pool_size нельзя вывести из материала.
- **Assumption silence**: предполагается, что startup-задачи завершатся до первого запроса, хотя `await` отсутствует.
- **Consequence silence**: утечка PII через `/rest/user/data-export` / `/rest/order-history` при IDOR — необратима после выдачи ответа.

[INTERSECTION_RISKS]
- Wildcard CORS × cookie-auth без SameSite → cross-origin чтение аутентифицированных ответов.
- `app.locals` global state × параллельные запросы → privilege escalation через `abused_ssti_bug`.
- Fire-and-forget startup × ранний трафик → работа с невалидной конфигурацией.
- `compression()` × Prometheus `/metrics` → потеря scrape-данных.
- Monkey-patch `res.end` × Express upgrade → тихий слом листинга директорий.

[ASSEMBLY] Иерархия: **core** (Express app + HTTP server, middleware chain, startup orchestration) → **service** (60+ route handlers, 18 Sequelize-моделей, websocket events, 4 static file servers) → **infra** (Prometheus, morgan + file-stream-rotator, config module, filesystem, DB). Критический путь: `module load → app/server → startup (fire-and-forget) → configureApp → middleware → routes → listen`. Циклов не обнаружено.

[REFACTORING] Три варианта:
- **A: Hardening in-place** (effort S, risk low) — точечные правки `server.ts`: `await` startup, CORS whitelist, request-scoped state, `import errorhandler`, убрать monkey-patch. Минимальный blast radius, но не решает multi-instance.
- **B: Bootstrap refactor + AsyncLocalStorage** (effort L, risk medium) — разделить `server.ts` на bootstrap/middleware/routes/startup, ввести `AsyncLocalStorage` для captcha и security-флагов, fail-fast startup. Готовность к горизонтальному масштабированию, но требует правок в `routes/*`.
- **C: Edge-offload** (effort M, risk medium) — вынести CORS/rate-limit/compression/TLS на reverse-proxy. Не решает startup-порядок и `app.locals` — отвергнут как достаточный (second_opinion SRE).

**Collision resolution**: 2 критичных конфликта Analyst↔Synthesizer. Приоритет — Analyst: `await` startup обязателен даже в варианте A; `app.locals` → request-scoped обязателен; вариант C отвергнут как достаточный. Оптимально — комбинация A+C (edge для CORS/rate-limit + in-place для startup/app.locals), не проверено.

[PARALLELS] Juice Shop — учебный проект: часть уязвимостей (wildcard CORS, отключённый xssFilter, monkey-patch) намеренна для обучения. В production-контексте те же паттерны — критичны. Параллель с типичными Express-бутстрапами: god-file `server.ts` — распространённый антипаттерн; `app.locals` для security-флагов — редкий и опасный выбор.

[TESTS] В slice тестов нет. Требуются: unit (middleware CORS/helmet/rateLimit), integration (startup-порядок: `validateConfig` до `listen`), security (IDOR, path traversal, SQLi через finale-rest), contract (idempotency на `/rest/order`), load (compression + Prometheus под нагрузкой). Edge cases: дублированные слэши в URL, пустой Origin, одновременные запросы к captcha, zip с `..` в именах, YAML с anchors (billion laughs).

[ACTION]
- **NOW**: `await` на трёх startup-задачах с fail-fast (`process.exit(1)` при падении `validateConfig`); readiness-gate до `listen`.
- **TODAY**: CORS whitelist через `config.get('application.allowedOrigins')`; `import errorhandler` вместо `require()`; фильтр `compression()` по Content-Type (исключить `/metrics`).
- **TOMORROW**: `AsyncLocalStorage` для `captchaId` / `abused_ssti_bug` / `abused_ssrf_bug`; убрать monkey-patch `res.end` через штатный serve-index API.
- **LATER**: `/healthz` + `/readyz`; timeout ≤ 10s на DB/внешние API/HTTP; circuit breaker для payment/web3/delivery; Idempotency-Key на `/rest/order`.

[QUESTIONS]
1. Есть ли внешние потребители API (сторонние интеграции), или CORS можно убрать полностью?
2. `config/default.yml` — содержит ли дефолтные секреты? (VERIFY)
3. `rateLimit` применён глобально или точечно? (VERIFY)
4. `finale-rest` auto-endpoints — параметризован ли SQL? (VERIFY)
5. Websocket trust boundary (TB6) и внешние сервисы (TB7) — расширять slice?
6. Целевой SLO: latency p95, error rate, availability?

[FUNC:FULL]
- **ECON**: effort — вариант A ~1–2 дня, B ~1–2 недели, C ~3–5 дней; cost — не определено (нет данных об инфраструктуре); ROI — высокий для A (устраняет 3 критичных дефекта при минимальном blast radius); budget — не задан; cloud delta — $0 (no infrastructure change); cost of delay — критично: каждый день с wildcard CORS + fire-and-forget startup = экспозиция API и риск работы с невалидной конфигурацией.
- **FAIL**: критично — startup без `await` (сервер стартует при падении `validateConfig`); `app.locals` shared state (cross-request privilege escalation); wildcard CORS (глобальная экспозиция). Cascade: падение `validateConfig` → невалидная конфигурация → дефолтные секреты → компрометация. Recovery: откат артефакта `server.ts` атомарен для варианта A; для B — согласованный откат `server.ts` + `routes/*` (риск частичного отката).
- **METRICS**: codebase — 1 файл, 60+ импортов, ~25 middleware, 18 моделей, 60+ routes; deps — 60, outdated/CVE не определено (нет lockfile в slice); tests — 0 в slice; perf — не определено (нет RPS); quality — `resilience_score=4/10`, `evolvability=3/10`; infra — pool_size=50 (нижняя граница), CPU/memory/autoscaling не определено.
- **ALTERNATIVES**: языки — не применимо (TS/Node зафиксирован); фреймворки — Express (текущий) vs Fastify (лучшая производительность, но миграция 60+ routes); БД — SQLite/Postgres через Sequelize (текущий); инфра — edge-offload (nginx/Envoy) для CORS/rate-limit/compression; паттерны — AsyncLocalStorage для request-scoped state, DI для route handlers, fail-fast bootstrap.
- **EVOLVE**: coupling — высокий (concrete imports из `./routes/*`, `./models/*`, `./lib/*`); abstractions — слабые (нет DI, нет интерфейсов); growth — добавление фичи требует правки корня (`server.ts`); friction — god-file, 60+ импортов, module-scope side effects (`fs.readFileSync`, `config.get`, `new Prometheus.Gauge`).
- **COMPARE**: time — A ~1–2 дня, B ~1–2 недели, C ~3–5 дней; cost — не определено; risk — A low, B medium, C medium; complexity — A низкая, B высокая, C средняя. Рекомендация: A+C (edge для CORS/rate-limit + in-place для startup/app.locals) — не проверено, требует верификации.

[MANDATORY BASE]
1. **ECONOMICS**: time — вариант A ~1–2 дня, при условии, что правки ограничены `server.ts`; cost — не определено, при условии отсутствия данных об инфраструктуре; ROI — высокий для A, при условии устранения 3 критичных дефектов.
2. **RISKS**: критично — startup без `await`, wildcard CORS, `app.locals` shared state; важно — `require()` в ESM, monkey-patch `res.end`, отсутствие timeout/circuit breaker; при условии, что часть ослаблений намеренна (Juice Shop).
3. **INFRASTRUCTURE**: pool_size=50, при условии нижней границы из constraints; replicas ≥2, при условии варианта B/C; CPU/memory/autoscaling — не определено, при условии отсутствия RPS.
4. **CODE**: change — `server.ts` (вариант A) или `server.ts` + `routes/*` (вариант B), при условии выбора варианта; 60+ импортов, ~25 middleware, 18 моделей.
5. **ACTION**: now — `await` startup с fail-fast; tomorrow — CORS whitelist, `import errorhandler`, фильтр `compression()`.
6. **TIMELINE**: NOW — `await` startup; TODAY — CORS whitelist, `import errorhandler`; TOMORROW — `AsyncLocalStorage`, убрать monkey-patch; LATER — `/healthz`, timeout, circuit breaker, idempotency.
7. **PRODUCTION IMPACT**: users — все (blast radius = 100%, bootstrap-файл); deploy window — не определено; rollback — атомарен для варианта A, риск частичного отката для B.
8. **SLO IMPACT**: current — не определено (SLO не заданы); after — не определено, при условии внешней верификации latency p95 / error rate / availability.
9. **CLOUD COST**: current — не определено; projected — не определено; delta ±$0, при условии отсутствия изменений инфраструктуры (mode_cost не запускался, spec пустой).
10. **ON-CALL**: new alerts — падение startup-задач, 5xx > 1% за 5 мин, недоступность `/metrics`; runbook — отсутствует; escalation — не определена.

[REFLEXION]
1. **Слабое место**: stage3 (researcher) отсутствует, но stage4 ссылается на «researcher: не применимо» в collision — это корректно, но создаёт асимметрию в разрешении конфликтов. **Исправлено**: в [ROUTE] и [REFACTORING] явно указано, что stage3 пропущен (research_first=false), конфликты разрешены по правилу «приоритет Analyst».
2. **Слабое место**: числа `pool_size=50`, `resilience_score=4`, `evolvability=3` взяты из stage4 без источника в материале. **Исправлено**: в [MANDATORY BASE] каждое число сопровождено условием («при условии нижней границы из constraints», «при условии отсутствия RPS»).
3. **Слабое место**: `force_emergency=true` из stage4 — но материал не содержит emergency-маркеров (нет падений, нет инцидента). **Исправлено**: `force_emergency` интерпретирован как сигнал от stage4 (2 критичных конфликта), а не как emergency материала; в [ACTION] приоритет отдан критичным дефектам, но без режима INTERRUPTED.

**Итог**: accepted.

---

*Audit-trail добавляется pipeline'ом (orchestrator.py) после Stage 5 — с реальными sha256, pii_detected, compliance_flags.*

[AUDIT_TRAIL]
audit_id: audit-2026-10-10-0060c1
material_hash: sha256:cf509023c0b15e3a45ab5ba75b680f314fa6cf2f1d2c2c7077cce33f1dd5cbe6
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

    vishap analyze data/real_cases/juice-shop/server.ts
