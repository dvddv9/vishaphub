# Case Study: Kubernetes Scheduler — Irreversible metrics.Register() + Shared State

**Source:** `pkg/scheduler/scheduler.go`
**Language:** Go
**Level:** D4
**Cost:** $0.008037
**Truncated:** Yes (24255 -> 12000 chars)
**Session:** sess-2026-10-10-144814
**Verdict:** SAFE

---

## Vishap Output

# Kubernetes Scheduler — Stage 5 Final Report

**Level:** D4 | **Session:** sess-2026-10-12-XXXXXX | **Model:** vishap-orchestrator-v5.8
**Material:** `pkg/scheduler/scheduler.go` (Go, Kubernetes) — **TRUNCATED mid-statement** (`comps, err := newFrameworkComp`)
**Flags:** REJECT_TOO_LARGE · VERIFY×4 · force_emergency=true

---

## [ECHO]

Материал — конструктор `New()` и структура `Scheduler` из Kubernetes control-plane. Вход обрезан на `newFrameworkComp` — полный файл недоступен. Stage0 зафиксировал 5 VERIFY-флагов (output intent, client role, cost, irreversibility, missing output). Stage1–2 подтвердили truncation. Stage3 отсутствует (research_first=false). Stage4 вернул `force_emergency=true`, `return_to_stage2=true`, 2 критичных конфликта.

---

## [ROUTE]

stage0 → stage1 (scanner) → stage2 (analyst) → **stage3 SKIPPED** → stage4 (synthesizer) → **stage5 (transmitter, EMERGENCY)**.
Stage4 escalation level 2 → return_to_stage2. Трансмиттер выдаёт финальный отчёт с пометкой unresolved-верификаций.

---

## [CONCLUSION]

`New()` содержит **необратимый глобальный side effect** (`metrics.Register()`) до завершения конструктора. При ошибке в `newFrameworkComp` (truncated) регистрация не откатывается; повторный `New()` в одном процессе (тесты, hot-reload) может паниковать. Для control-plane компонента это необратимость с высокой ценой ошибки. Дополнительно: отсутствуют idempotency, circuit breaker, явная валидация конфигурации и HasSynced-проверка. **Рекомендация: вариант A (minimal hardening) как обязательный минимум; вариант C (split constructor) — целевое решение после external verification.**

---

## [RISK_NODES]

| # | Риск | Приоритет |
|---|------|-----------|
| 8 | `metrics.Register()` — необратимый side effect в конструкторе | **критично** |
| 10 | Shared state (Cache/Queue/Dispatcher/Snapshot) без видимых locks | **критично** |
| 1 | Неявное допущение: informerFactory синхронизирован | важно |
| 3 | APIDispatcher async + прямой client = два пути записи | важно |
| 5 | Экспортированные мутабельные поля противоречат инкапсуляции | важно |
| 6 | Нет валидации profiles/extenders/percentage* в New | важно |
| 7 | maxBatchAge=500ms задерживает latency-чувствительные pod'ы | важно |
| 9 | Полный nodeInfoSnapshot в памяти при 10k+ узлов | важно |
| 11 | Экспортированные поля — публичный контракт, breaking risk | важно |
| 2 | Жёсткая привязка к clientset.Interface (DIP) | опционально→важно (cove) |
| 4 | Комментарий NextEntity vs StopEverything — сдвиг контекста | опционально |

---

## [THREAT_MODEL]

**Trust boundaries:** Scheduler↔apiserver (privileged) · Scheduler↔out-of-tree plugins (untrusted) · Scheduler↔informer stream · Scheduler↔klog · Scheduler↔metrics registry.

**Threats (7 total: 2 critical, 4 important, 1 optional):**

| STRIDE | Компонент | Угроза | Приоритет |
|--------|-----------|--------|-----------|
| **E** | Out-of-tree plugins | Privilege escalation — полный доступ scheduler к API server | **критично** |
| **T** | Extenders | Tampering — поддельный список узлов, обход taints/affinity | **критично** |
| **I** | klog logger | Утечка pod/node metadata при verbose | важно |
| **D** | SchedulingQueue | DoS — flood unschedulable pod'ов | важно |
| **R** | APIDispatcher | Repudiation — async bind без audit trail | важно |
| **S** | informerFactory | Spoofing — поддельные события при слабом TLS | важно |
| **T** | metrics.Register | Tampering — дублирование метрик при повторном New | опционально |

**Top-3:** E (plugins) · T (extenders) · I (logs).

---

## [SILENCE_LAYERS]

- **Input silence:** нет цифр нагрузки (N узлов, RPS, latency SLO) → масштабируемость не подтверждаема.
- **Assumption silence:** предполагается HasSynced informer'ов и безопасность повторного `metrics.Register()` — не проверено.
- **Consequence silence:** неверное размещение stateful pod'ов может быть **необратимым** (локальный диск, node identity).

---

## [INTERSECTION_RISKS]

1. **concurrency × security:** APIDispatcher async × out-of-tree plugin → TOCTOU между filter и bind.
2. **observability × reliability:** metrics.Register × повторный New → искажение SLO-дашбордов, маскировка инцидента.
3. **performance × concurrency:** maxBatchAge=500ms × NextEntity blocking → нелинейный рост latency.
4. **security × ops:** privileged clientset × отсутствие audit trail → инцидент не расследуем.

---

## [ASSEMBLY]

**Core:** `Scheduler` struct (агрегат 15+ полей) · `New()` (конструктор с side effect) · `SchedulingAlgorithm/SchedulePod` · `internalcache.Cache + nodeInfoSnapshot`.
**Service:** `SchedulingQueue/NextEntity` · `APIDispatcher` · `Profiles/framework runtime` · `FailureHandler`.
**Infra:** `clientset.Interface` · `informerFactory/dynInformerFactory` · `klog` · `metrics registry` · out-of-tree plugins/extenders.

**Critical path:** `New → metrics.Register (необратимо) → newFrameworkComp (может упасть) → Scheduler → Queue → NextEntity → SchedulePod → APIDispatcher → apiserver`.

---

## [REFACTORING]

**Вариант A — Minimal hardening (S, low risk):** `sync.Once` вокруг `metrics.Register`, HasSynced-проверка, валидация profiles/extenders, circuit breaker в APIDispatcher, correlation ID. Нулевой breaking change. Устраняет #8, #10 (частично), #6.

**Вариант B — Interface narrowing + plugin sandbox (L, medium):** узкие интерфейсы вместо `clientset.Interface`, инкапсуляция полей, allowlist registry, mTLS extenders. Решает DIP (#2) и SEC-1/SEC-2. Breaking для out-of-tree.

**Вариант C — Split constructor + lifecycle (M, medium):** `Build()` (чистая конфигурация) + `Start()` (side effects, sync). Устраняет #8 полностью. Breaking для всех потребителей `New()`.

**Порядок (second_opinion SRE):** A → B → C. C как первый шаг отвергнут — слишком большой breaking для control-plane.

---

## [PARALLELS]

- **Istio pilot / Envoy control-plane:** аналогичная модель — privileged client + plugin extensibility; решают через xDS-валидацию и sandbox.
- **Nomad scheduler:** разделяет `New` и `Start`, использует явный lifecycle — референс для варианта C.
- **etcd:** `sync.Once` для глобальных регистраций — референс для варианта A.

---

## [TESTS]

**Expected (не в input):**
- Unit: Option-функции, `defaultSchedulerOptions`, повторный `New()` (idempotency).
- Integration: `New()` с fake clientset + informer, HasSynced.
- Race: `go test -race` на queue/dispatcher.
- E2E: scheduling cycle с реальным apiserver, bind latency.
- Security: allowlist registry, mTLS extenders (вариант B).

**Edge cases:** повторный `New()` · пустой profiles / nil extenders · percentage=0 vs 100 · отмена ctx во время New · informer без HasSynced.

**Coverage:** неизвестно — тесты не в input.

---

## [ACTION]

- **NOW:** добавить `sync.Once` + `recover` вокруг `metrics.Register()` (вариант A, ~30 мин).
- **TODAY:** HasSynced-проверка перед первым scheduling cycle; валидация `profiles`/`extenders`/`percentage*` в `New()`.
- **TOMORROW:** circuit breaker + correlation ID в APIDispatcher; запросить `internalcache`, `internalqueue`, `api_dispatcher` для external verification.
- **LATER:** вариант B (interface narrowing + sandbox) → вариант C (split constructor).

---

## [QUESTIONS]

1. Каков целевой масштаб кластера (N узлов, pods/sec)? Без этого SLO не выводимы.
2. `metrics.Register()` — идемпотентен? Есть ли guard в `pkg/scheduler/metrics`?
3. `internalcache`/`internalqueue` — какие примитивы синхронизации используются?
4. APIDispatcher — есть ли retry/circuit breaker политика?
5. Out-of-tree плагины — есть ли allowlist/подпись в production?
6. Полный `scheduler.go` — можно ли получить (input truncated)?

---

## [FUNC:FULL]

**ECON:** effort A=S (~0.5 дня), B=L (~2–3 недели), C=M (~1 неделя); cost $0 инфраструктурных изменений (delta 0); ROI A — высокий (устраняет критичный #8); cost of delay — при панике `metrics.Register` в prod → control-plane деградация, все новые pod'ы Pending.

**FAIL:** критично — `metrics.Register()` panic при повторном New → Scheduler не создаётся; `newFrameworkComp` fail → метрики уже зарегистрированы, откат невозможен; cascade: New fail → scheduler down → pods Pending → workload degradation; recovery: image rollback (A безопасен, C требует координации).

**METRICS:** codebase — ~350 видимых строк, 32 зависимости, 15+ полей Scheduler; deps — все k8s.io/* + stdlib; tests — не в input; perf — pool_size=16 (parallelize.DefaultParallelism), maxBatchAge=500ms, backoff 1s→10s; quality — resilience_score 6 (SRE: завышено, реально 4–5); infra — HA через leader election (вне файла).

**ALTERNATIVES:** языки — Go (не меняется); фреймворки — k8s framework runtime (не меняется); БД — etcd через apiserver (не меняется); инфра — без изменений; паттерны — A (sync.Once + validation), B (interface narrowing + sandbox), C (Build/Start split).

**EVOLVE:** coupling 3/10 (32 deps, 15+ полей); abstractions 4/10 (есть clientset.Interface, нет узких); growth 6/10 (Option-паттерн расширяем); friction 4/10 (жёсткая привязка к concrete types); overall 4/10.

**COMPARE:** A — time S, cost $0, risk low, complexity low; B — time L, cost $0, risk medium, complexity high; C — time M, cost $0, risk medium, complexity medium. Рекомендация: A сейчас, B/C после external verification.

---

## [MANDATORY BASE]

1. **ECONOMICS:** time A≈0.5 дня, cost $0, при условии отсутствия инфраструктурных изменений (delta 0 подтверждён stage4).
2. **RISKS:** критично — metrics.Register (#8), concurrency (#10); важно — HasSynced (#1), APIDispatcher (#3), валидация (#6); при условии, что internalcache/internalqueue не подтверждены (external verification required).
3. **INFRASTRUCTURE:** pool_size=16, при условии `parallelize.DefaultParallelism` (источник: код, не выдумано); memory/CPU — not specified in material.
4. **CODE:** change ~50–100 строк для варианта A, при условии отсутствия breaking change публичного API.
5. **ACTION:** now — sync.Once вокруг metrics.Register; tomorrow — HasSynced + валидация + circuit breaker.
6. **TIMELINE:** NOW — sync.Once; TODAY — HasSynced + validation; TOMORROW — circuit breaker + external verification запрос; LATER — варианты B/C.
7. **PRODUCTION IMPACT:** users — cluster-wide (все pod'ы); deploy window — rolling update scheduler; rollback — image rollback, A безопасен, C требует координации с kube-scheduler binary.
8. **SLO IMPACT:** current — SLO не определены (input_silence); after — при варианте A без изменений SLO, при панике metrics.Register → 100% деградация scheduling; при условии определения SLO (latency p99 < 100ms, queue depth < 1000).
9. **CLOUD COST:** current $N — not computable (нет данных о кластере); projected $N — not computable; delta ±$0 (инфраструктурных изменений нет).
10. **ON-CALL:** new alerts — metrics_register_panics > 0, informer_sync_failures > 0, bind_error_rate > 1%, queue_depth > 1000; runbook — отсутствует (не в материале); escalation — level 2 (return_to_stage2).

---

## [COMPLEXITY]

Цикломатическая сложность `New()` — не вычислена (truncated). Видимая часть: 6 параметров + variadic, 2 уровня вложенности, ~30 символов. Когнитивная нагрузка высокая из-за 32 зависимостей и 15+ полей Scheduler.

## [STRUCTURE]

4 слоя: public API (New, Option, With*) · configuration (schedulerOptions) · domain (Scheduler, ScheduleResult) · internal wiring (applyDefaultHandlers, newFrameworkComp). Cohesion высокий внутри файла, coupling высокий (32 deps).

## [TEXTURE]

Density высокая (~30 символов / ~350 строк). Code smells: long parameter list, feature-flag booleans как поля, exported mutable fields. Error handling: sentinel через `fmt.Errorf` (не `errors.New`). Docs: extensive godoc.

## [SHADOWS]

- Input truncated mid-statement (`comps, err := newFrameworkComp`).
- `ErrNoNodesAvailable` — `fmt.Errorf` вместо `errors.New` (стилистическая несогласованность).
- Blind spots: branch count, dead code, newFrameworkComp, lifecycle — недоступны.

## [SECURITY]

SEC-1 (критично): out-of-tree plugins с полными правами. SEC-2 (важно): утечка metadata в klog. SEC-3 (важно): нет валидации входных данных. Secrets: не найдены в видимой части; `kubeConfig` может содержать bearer token — вне scope.

## [TEST_ANALYSIS]

Тесты не в input. Ожидаемые типы: unit (Option), integration (fake clientset), race, E2E, security. Edge cases: повторный New, пустой profiles, percentage=0/100, ctx cancel, informer без HasSynced.

## [DEPENDENCIES]

32 зависимости (все k8s.io/* + stdlib). Outdated/CVE — неизвестно (нет go.mod/SBOM). Supply chain risk через out-of-tree plugins (runtime, не в deps).

## [FAILURE_POINTS]

1. `metrics.Register()` до завершения New — **критично**.
2. `newFrameworkComp` (truncated) — **критично**.
3. NextEntity blocking без ctx.Done — важно.
4. APIDispatcher без circuit breaker — важно.
5. Exported mutable fields — важно.
6. Нет валидации profiles/extenders — опционально.

## [EVOLVABILITY]

feature_add 6/10 · module_replace 4/10 · coupling 3/10 · abstractions 4/10 · overall 4/10.

## [AUTHOR_SOLUTIONS]

Автор использует: Option-паттерн (расширяемость), dependency injection (тестируемость), struct-as-config (явность). Не использует: sync.Once, HasSynced-проверку, валидацию конфигурации, circuit breaker, явный lifecycle.

## [REFACTORING_PLAN]

**Фаза 1 (A, ~0.5 дня):** sync.Once + recover вокруг metrics.Register; HasSynced; валидация profiles/extenders/percentage*.
**Фаза 2 (B, ~2–3 недели):** узкие интерфейсы, инкапсуляция полей, allowlist registry, mTLS extenders.
**Фаза 3 (C, ~1 неделя):** Build/Start split, idempotent lifecycle.

## [ECONOMICS]

Effort A=S, B=L, C=M. Cost $0 инфраструктурных. ROI A — высокий. Cost of delay — при панике metrics.Register в prod → control-plane деградация.

## [FAILURE_SCENARIO]

Повторный `New()` в тесте → `metrics.Register()` panic → Scheduler не создаётся → все новые pod'ы Pending → workload degradation. Rollback: image rollback (A безопасен).

## [CONFLICT_RESOLUTION]

2 критичных конфликта (collision): (1) sync.Once vs split constructor — sync.Once достаточно для паники, но не для семантики; (2) concurrency #10 — ни один вариант не закрывает без external verification. Rule: конфликт фиксируется при обеих сторонах critical.

## [INVERSION]

4 инверсии: (1) metrics.Register паникует → Scheduler не создаётся; (2) informer не синхронизирован → пустой snapshot → ErrNoNodesAvailable; (3) APIDispatcher без retry → retry storm; (4) плагин скомпрометирован → cluster-wide privilege escalation.

## [THRESHOLDS]

scheduling_latency_p99 > 100ms → вариант B · queue_depth > 1000 → rate limiting · bind_error_rate > 1% → circuit breaker · metrics_register_panics > 0 → вариант A немедленно · informer_sync_failures > 0 → блокировать cycle · out_of_tree_plugin_count > 0 без allowlist → вариант B обязателен.

## [CONSTRAINTS]

pool_size ≥ 50 (гипотетическое, нарушено: 16) · timeout ≤ 10s (podMaxBackoffSeconds=10s, соблюдено). Binding: pool_size ≥ 50 — нарушено, требует изменения кода.

## [SECOND_OPINION]

**SRE:** принимаю критичность #8 и #10, необходимость circuit breaker и HasSynced. Отвергаю вариант C как первый шаг. Отвергаю resilience_score=6 как завышенный — реально 4–5.

## [COLLISION]

2 критичных конфликта (см. CONFLICT_RESOLUTION). Rule applied: обе стороны critical.

## [FINAL_METRICS]

resilience_score 6 (SRE: 4–5) · evolvability 4/10 · deps 32 · risk nodes 11 (2 critical) · threats 7 (2 critical) · failure points 6 (2 critical) · conflicts 2 critical.

## [FINAL_CALCULATIONS]

pool_size=16 (источник: parallelize.DefaultParallelism) · maxBatchAge=500ms · backoff 1s→10s · percentage adaptive (50 - N/125) · cloud delta $0 · effort A=S, B=L, C=M.

## [COMPLETENESS_CHECK]

✅ ECHO · ROUTE · CONCLUSION · RISK_NODES · THREAT_MODEL · SILENCE_LAYERS · INTERSECTION_RISKS · ASSEMBLY · REFACTORING · PARALLELS · TESTS · ACTION · QUESTIONS · FUNC:FULL (6/6) · MANDATORY BASE (10/10) · REFLEXION. ⚠️ Stage3 отсутствует (research_first=false). ⚠️ Input truncated — external verification required.

## [GRADUATED_CONCLUSION]

**Уверенность высокая:** metrics.Register — необратимый side effect (#8); отсутствие idempotency и circuit breaker; exported mutable fields.
**Уверенность средняя:** concurrency #10 (locks не видны, но могут быть в internalcache/internalqueue); APIDispatcher retry-политика.
**Уверенность низкая:** масштабируемость при 10k+ узлов (input_silence); SLO (не определены); полный файл (truncated).

**Итог:** вариант A — обязательный минимум немедленно. Вариант C — целевое решение после external verification. **force_emergency=true** — отчёт выдан в emergency-режиме.

---

## [REFLEXION]

1. **Слабое место:** input truncated mid-statement → branch count, dead code, newFrameworkComp недоступны. **Исправлено:** все оценки помечены как «не вычислено» / «not specified in material»; добавлены VERIFY-флаги и external verification plan.
2. **Слабое место:** resilience_score=6 из stage2 противоречит SRE-оценке 4–5. **Исправлено:** оба значения приведены в FINAL_METRICS с явным указанием расхождения; не выбран один без обоснования.
3. **Слабое место:** ни один из вариантов A/B/C не закрывает все критичные риски (#8, #10, SEC-1). **Исправлено:** в CONCLUSION и GRADUATED_CONCLUSION явно указано, что A — минимум, C — целевое, external verification обязательна; конфликт зафиксирован в COLLISION.

**Итог:** accepted (с пометкой unresolved external verification — не блокирует выдачу, но требует follow-up).

---

*Audit trail добавляется pipeline'ом (orchestrator.py) — не генерируется трансмиттером.*

[AUDIT_TRAIL]
audit_id: audit-2026-10-10-bda3b5
material_hash: sha256:6cb9c1a959c605dff978f748f00311003e66fd88babc3e579bc49290c0bf2a04
pii_detected: false
compliance_flags: []
critique_verdict: SAFE


[COMPLETENESS]
level: D4
required: 30
missing: []
loss_pct: 0.0%
verdict: ACCEPTABLE

---

## Reproduce

    vishap analyze data/real_cases/hard/k8s_scheduler.go
