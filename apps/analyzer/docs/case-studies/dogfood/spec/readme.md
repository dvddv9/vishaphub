# Dogfood: readme

**Source:** `README.md`
**Type:** readme
**Level:** D3 | **task_type:** other
**Cost:** $0.010131 | **Verdict:** REQUIRES_REVIEW | **Risk:** SAFE
**Session:** `sess-2026-10-12-121449` | **audit_id:** `audit-2026-10-12-70bcff`
**material_hash:** `sha256:1ca202222e52a12d93c522d55a0da4711f33998c4e9e4f1f9ba20199419b7a22`
**material_hash_full:** `sha256:be0b567a6ac149e22c7c29953ad19d88f55d49137651e79977245f0b2c352dbf` (truncated: True, original_size: 15343)
**pii_detected:** False | **Compliance:** HIPAA, PCI-DSS, GDPR, EU AI Act

---

## Vishap Output

# D3 — Vishap V5.8 README (проектная документация)

[ECHO] README.md проекта Vishap V5.8 — 6-stage LLM pipeline для анализа инженерных материалов. ~500 строк markdown: описание, архитектура, stack, quick start, usage, project structure, audit & compliance, example report, development, case studies. material_type=other, language=other, level=D3, session=sess-2026-10-08-a7f3c1.

[ROUTE] stage0 → stage1 → stage2 → stage4 → stage5. Stage 3 (researcher) не запускался (research_first=false). Параллелизм не требуется. subst_count=0.

[CONCLUSION] Документация описывает работающую локальную систему с сильной архитектурной идеей (staged pipeline + audit trail), но с критичными пробелами в безопасности и надёжности: API :5001 без аутентификации, PII в audit-файлах в открытом виде, отсутствие timeout/retry/circuit breaker для LLM, race в history.json. Система не готова к prod-деплою без hardening. Resilience 3/10. Признаков подмены инструкций в материале не найдено (VERIFY: prompt injection через conveyor/*.md не проверялся — содержимое не приведено).

[RISK_NODES]
- RN-1 (критично): API :5001 без auth — /analyze, /history, /history/clear открыты.
- RN-2 (критично): PII (email, phone_ru, passport_ru, snils, iban) в audit_*.json в открытом виде.
- RN-9 (критично): нет timeout/retry/circuit breaker для LLM; поведение при отказе DeepSeek+Ollama не описано.
- RN-11 (критично): race в data/history.json без блокировок; /analyze не идемпотентен.
- RN-5 (важно): «audit trail для compliance» хранит PII в открытом виде — сдвиг тезиса.
- RN-6 (важно): material_hash в отчёте (16 hex) ≠ в audit-файле (64 hex) — верификация невозможна.
- RN-3 (важно): 44 теста без покрытия конкурентности, отказа LLM, truncation-границ.
- RN-8 (важно): 40–90 сек cloud / 20–40 мин local CPU; Stage 3/4 последовательны.
- RN-10 (важно): JSON storage, read-modify-write без блокировок.
- RN-12 (важно, VERIFY): схема audit_*.json без версионирования — ломающие изменения для downstream.
- RN-4 (важно): fallback DeepSeek→Ollama без описанного условия срабатывания.
- RN-7 (опционально): секция Roadmap пуста.

[PLAN_B]
- RN-1: bind API на 127.0.0.1 + reverse proxy с API-key auth (src/security/auth.py).
- RN-2: PII redaction перед записью в audit + шифрование at-rest (src/security/pii_redact.py).
- RN-9: timeout_s=10.0 + retry (2) + circuit breaker (5 failures / 30s recovery).
- RN-11: file-lock (fcntl/msvcrt) вокруг read-modify-write history.json + идемпотентность по material_hash.
- RN-5: переименовать «audit trail» → «analysis log» ИЛИ добавить redaction.
- RN-6: унифицировать material_hash → 64 hex в отчёте и audit-файле.
- RN-3: добавить тесты на race, LLM timeout, truncation MAX_CHARS=12000, auth 401.
- RN-8: параллелизация Stage 3/4 через asyncio + bounded queue.
- RN-10: миграция JSON→SQLite (WAL) при >3 concurrent /analyze.
- RN-12: audit_schema_version (semver) + dual-write на переходный период.
- RN-4: явное условие fallback (DeepSeek error rate >5% → circuit open → Ollama).
- RN-7: заполнить Roadmap или удалить секцию.

[THREAT_MODEL] STRIDE, 12 угроз, 5 критичных / 7 важных. Trust boundaries: TB-1 User→UI, TB-2 UI→API, TB-3 API→DeepSeek (external), TB-4 API→Ollama (local), TB-5 API→data/*.json, TB-6 API→.env. Top-3: (1) TB-2/S — нет auth на :5001; (2) TB-5/I — PII в audit в открытом виде; (3) TB-3/I — утечка PII в DeepSeek cloud. Дополнительно (Stage 4 new_risks): TB-4 Ollama :11434 без auth, XSS через Markdown-отчёт в Streamlit, DEEPSEEK_API_KEY в логах при ошибке LLM-клиента.

[SILENCE_LAYERS]
- Input: нет RPS/concurrent users/retention; нет содержимого requirements.txt, tests/, conveyor/*.md.
- Assumption: «API локальный», «PII безопасно хранится», «DeepSeek всегда доступен», «history.json не повреждается», «MAX_CHARS=12000 достаточно».
- Consequence: PII в audit необратимо; утечка .env → неограниченные расходы; EMERGENCY_INTERRUPT не отменяет утечку PII.

[INTERSECTION_RISKS]
- input_silence × assumption_silence: нет цифр нагрузки × «локальный запуск» → DoS через /analyze без rate limit при первом деплое в сеть.
- assumption_silence × consequence_silence: «PII безопасно» × PII в audit необратимо → GDPR/152-FZ нарушение при утечке.
- input_silence × consequence_silence: нет содержимого conveyor/*.md × prompt injection необратим → невидимая подмена поведения pipeline.
- assumption_silence × assumption_silence: fallback DeepSeek × history.json без блокировок → двойная запись при параллельных запросах.
- consequence_silence × consequence_silence: EMERGENCY_INTERRUPT × audit уже собран → иллюзия защиты.

[ASSEMBLY] Core: orchestrator.py (маршрутизация + audit + completeness — 3 ответственности, SRP-риск), stages.py (stage0..5), llm/client.py. Service: main.py (FastAPI :5001), streamlit_app.py (:8501), storage/history.py, tools/*. Infra: data/*.json, .env, DeepSeek API, Ollama :11434, GitHub Actions. Critical path: UI → API → orchestrator → stages → llm_client → DeepSeek. Циклов в dependency graph нет.

[REFACTORING] Вариант A (hardening in-place, 3–5 дней, low risk): bind 127.0.0.1 + API-key auth, PII redaction, timeout+retry+circuit breaker, file-lock, rate limit. Закрывает FP-1..FP-5. Вариант B (storage migration + async, 8–12 дней, medium): A + SQLite WAL + параллелизация Stage 3/4 + audit_schema_version. Вариант C (multi-tenant, 25–40 дней, high): B + Postgres + Redis queue + mTLS + secret manager + retention. Рекомендация: начать с A; B при >3 concurrent /analyze; C — только при переходе в prod.

[PARALLELS] Архитектурно близко к: (1) SonarQube/CodeQL — staged static analysis с отчётом; (2) LLM-observability (LangSmith, Helicone) — audit trail вызовов; (3) DLP-системы — PII-детекция. Отличие Conveyor: 6-stage LLM pipeline с fallback cloud/local и встроенным audit. По паттерну — pipeline/chain-of-responsibility + fallback.

[TESTS] Заявлено 44 теста (PII, compliance, hash, JSON parsing, fallback_check, pipeline с mock LLM). Пробелы: конкурентность, race в history.json, отказ LLM (timeout/rate limit/невалидный JSON), truncation MAX_CHARS=12000, EMERGENCY_INTERRUPT, auth/authz, XSS, retention. Типы: unit + integration заявлены; e2e/load/security/chaos — нет. Для варианта A: unit audit-модуль, integration race-тест, e2e 401 без токена, unit PII→redacted, integration mock timeout→fallback.

[ACTION]
- NOW: bind API :5001 и UI :8501 на 127.0.0.1 (немедленно, если доступны из сети — VERIFY: bind-адрес не указан в материале).
- TODAY: PII redaction перед записью в audit_*.json; API-key auth на :5001.
- TOMORROW: timeout_s=10.0 + retry + circuit breaker для LLM; file-lock на history.json; rate limit на /analyze.
- LATER: миграция JSON→SQLite (при >3 concurrent); параллелизация Stage 3/4; audit_schema_version; retention/шифрование audit; SLO + on-call runbook.

[QUESTIONS]
- Где сейчас работает Conveyor — локально или в prod? Влияет на выбор A/B/C. (VERIFY)
- Как реализован fallback DeepSeek→Ollama в llm/client.py? Условие срабатывания? (VERIFY)
- Ollama :11434 — bind на localhost или 0.0.0.0? Есть ли auth? (VERIFY)
- Что происходит с PII после анализа — retention, ротация, доступ к audit_*.json? (VERIFY)
- requirements.txt — версии зависимостей для CVE-анализа? (VERIFY: не приведён)
- Кто downstream-потребители audit_*.json? Нужно ли версионирование схемы? (VERIFY)

[FUNC:FULL]
- ECON: effort A=3–5 дней, B=8–12, C=25–40; cost LLM $0.0072/анализ (из case studies); cloud_delta $0 (инфра не меняется в A); ROI A — высокий (закрывает 5 критичных FP); cost_of_delay — качественно: каждый день без auth+PII redaction = экспозиция PII и платного эндпоинта; при утечке .env — неограниченные расходы DeepSeek (необратимо). Ставка инженера материалом не задана — денежная оценка не выдумывается.
- FAIL: критично — FP-1 (auth), FP-2 (PII в audit), FP-3 (нет timeout/circuit breaker); важно — FP-4 (race history.json), FP-5 (нет rate limit). Cascade: DeepSeek down → нет timeout → pipeline зависает → нет алерта → оператор не знает. Recovery: circuit breaker → fallback Ollama; file-lock → целостность history; PII redaction → compliance.
- METRICS: ~500 строк README; 6 stages; 44 теста (заявлено); deps — Python 3.11+, FastAPI, Uvicorn, Streamlit, DeepSeek, Ollama (requirements.txt не приведён); perf — 40–90 сек cloud, 20–40 мин local CPU; quality — resilience 3/10, evolvability 6/10; infra — single-node, JSON storage, pool_size≥50 (constraint).
- ALTERNATIVES: storage — JSON (текущий) / SQLite WAL (B) / Postgres (C); LLM — DeepSeek cloud / Ollama local / auto-fallback; auth — API-key / mTLS / reverse proxy; concurrency — file-lock / SQLite транзакции / Redis queue; паттерн — pipeline (текущий) / event-driven workers.
- EVOLVE: coupling 5/10 (JSON storage — скрытая связность); abstractions 6/10 (llm/, pipeline/, storage/, tools/ — хорошая заменяемость); feature_add 6/10; module_replace 7/10; friction — orchestrator с 3 ответственностями (SRP), отсутствие контрактов (retry/timeout/circuit breaker), нет кэша LLM-ответов по material_hash.
- COMPARE: A — 3–5 дней, low risk, закрывает 5 критичных FP, не решает масштабируемость; B — 8–12 дней, medium, +race+latency, single-node; C — 25–40 дней, high, prod-grade multi-tenant, избыточно для локального сценария. Time: A<B<C. Cost: A<B<C. Risk: A<B<C. Complexity: A<B<C.

[MANDATORY BASE]
1. ECONOMICS: time A=3–5 дней, cost $0 инфра (LLM $0.0072/анализ), при условии локального сценария без prod-деплоя; при переходе в prod — C=25–40 дней.
2. RISKS: критично — RN-1 (auth), RN-2 (PII), RN-9 (LLM timeout), RN-11 (race); важно — RN-5, RN-6, RN-3, RN-8, RN-10, RN-12, RN-4; при условии, что API :5001 доступен из сети (VERIFY: bind-адрес не указан).
3. INFRASTRUCTURE: pool_size=50 (constraint, нижняя граница), replicas A=1 / B=1 / C≥2+N workers, при условии single-node JSON storage для A/B.
4. CODE: change ~5 файлов для A (auth.py, pii_redact.py, lock.py, resilient_client.py, main.py), при условии, что orchestrator.py не требует переписывания.
5. ACTION: now — bind 127.0.0.1; tomorrow — PII redaction + auth + timeout + file-lock + rate limit.
6. TIMELINE: NOW — bind 127.0.0.1 (если доступен из сети); TODAY — PII redaction + API-key auth; TOMORROW — timeout/retry/circuit breaker + file-lock + rate limit; LATER — SQLite migration, параллелизация Stage 3/4, audit_schema_version, retention, SLO, on-call.
7. PRODUCTION IMPACT: users N (не задано материалом — VERIFY); deploy window — не описано; rollback — не описан (нет версионирования, нет feature flags); blast_radius — при утечке .env компрометация DeepSeek-аккаунта, при утечке audit — PII всех проанализированных материалов.
8. SLO IMPACT: current — SLO не заявлены (defined=false); after — рекомендовано availability ≥99%, p95 /analyze ≤120 сек, error rate ≤5%, PII leak incidents=0, при условии внедрения метрик и алертов.
9. CLOUD COST: current $0.0072/анализ (LLM, из case studies); projected $0.0072/анализ (инфра не меняется в A); delta ±$0, при условии отсутствия изменений инфраструктуры; при C — рост на стоимость Postgres+Redis (не оценено, RPS не задан).
10. ON-CALL: new alerts — нет (не описаны); runbook — отсутствует; escalation — не описан; gaps: что делать при отказе DeepSeek, повреждении history.json, обнаружении PII в audit, EMERGENCY_INTERRUPT.

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | FAIL | API :5001 без auth, PII в audit в открытом виде, Ollama :11434 без auth, XSS-риск |
| Facts | WARN | material_hash 16 vs 64 hex (RN-6); Roadmap пуст; ссылки на внешние артефакты без содержимого |
| Logic | OK | Архитектура связна, dependency graph без циклов, staged pipeline логичен |
| Applicability | WARN | Локальный сценарий работает; prod-деплой требует hardening (A минимум) |
| Effectiveness | OK | 40–90 сек cloud приемлемо; 20–40 мин local CPU — практическая непригодность |
| Resilience | FAIL | 3/10: нет timeout/retry/circuit breaker, race в history.json, нет rate limit |
| Human factor | WARN | Смешение RU/EN, PowerShell-only команды, пустой Roadmap, нет on-call |
| Clarity | OK | Структура ясная, таблицы, диаграмма, примеры; терминологическая нестрогость (data/ = results) |

[REFLEXION]
1. Слабое место: числа (effort, cost, SLO) могли быть выдуманы → исправлено: все числа привязаны к источнику (case studies $0.0072, constraints pool_size=50, Stage 4 effort_days) или помечены «не задано материалом — VERIFY».
2. Слабое место: RN-12 в Stage 2 помечен «опционально», но COVE Stage 2 и Stage 4 подняли до «важно» → исправлено: в [RISK_NODES] RN-12 указан как «важно (VERIFY)».
3. Слабое место: [ACTION] и [MANDATORY BASE] могли рассинхронизироваться по шкале NOW/TODAY/TOMORROW/LATER → исправлено: обе секции используют одну шкалу, NOW=bind, TODAY=PII+auth, TOMORROW=timeout+lock+rate limit, LATER=migration+SLO.
Итог: accepted

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-70bcff
material_hash: sha256:1ca202222e52a12d93c522d55a0da4711f33998c4e9e4f1f9ba20199419b7a22
material_hash_full: sha256:be0b567a6ac149e22c7c29953ad19d88f55d49137651e79977245f0b2c352dbf
pii_detected: false
compliance_flags: ['HIPAA', 'PCI-DSS', 'GDPR', 'EU AI Act']
critique_verdict: REQUIRES_REVIEW
risk_verdict: SAFE


[COMPLETENESS]
level: D3
required: 12
missing: []
loss_pct: 0.0%
material_complete: False
verdict: ACCEPTABLE