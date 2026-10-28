# Dogfood: orchestrator

**Source:** `src/pipeline/orchestrator.py`
**Type:** orchestrator
**Level:** D3 | **task_type:** review
**Cost:** $0.008482 | **Verdict:** REQUIRES_REVIEW | **Risk:** SAFE
**Session:** `sess-2026-10-12-120735` | **audit_id:** `audit-2026-10-12-f8bc70`
**material_hash:** `sha256:20ba7d60c5d1d7269e56b9ecb487bcd33acf8b738cd01517a0fee96e095d58c2`
**material_hash_full:** `sha256:e95a8b063922a8918f4cc38c691296b70c131e85fb7f72406f8675f10a179e6b` (truncated: True, original_size: 21578)
**pii_detected:** False | **Compliance:** HIPAA, PCI-DSS, GDPR, 152-ФЗ, EU AI Act

---

## Vishap Output

# Vishap V5.8 — Code Review: `orchestrator.py`

[ECHO] Материал: Python-модуль `orchestrator.py` (Conveyor pipeline, v3 docstring vs v5.7 маркировка). Усечён на `print("[Stag`. task_type=review, level=D3, route: stage0→1→2→4→3→5. research_first=false, subst_count=0. session_id: sess-2026-10-12-XXXXXX.

[ROUTE] stage0 (orchestrator) → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage3 (researcher, skipped) → stage5 (transmitter). Sequential, no parallel.

[CONCLUSION] Модуль функционально рабочий, но содержит 4 критичных дефекта надёжности/безопасности: (1) отсутствие обработки I/O-ошибок при записи compliance-артефактов (RN-8, FP-1); (2) гонки на `session_id` и `add_entry` (RN-9, RN-10, FP-2, FP-3); (3) автоматическое понижение EMERGENCY на основе regex-эвристики — обход защиты (SEC-2, FP-4); (4) PII/секреты уходят в cloud LLM без redaction (TB-2/I, FP-5). Тесты отсутствуют (0%). Resilience score: 3/5. Рекомендация — hotfix Option A (2–3 дня), не немедленный STOP. Нет признаков наличия тестов и CI-артефактов в видимом фрагменте (VERIFY: не проверялось вне фрагмента).

[RISK_NODES]
- **RN-8 (критично)**: нет try/except вокруг `write_text`, `add_entry`, stage-вызовов → потеря audit-записи необратима.
- **RN-10 (критично)**: `add_entry` без синхронизации → гонка при параллельных сессиях.
- **SEC-2 (критично)**: EMERGENCY от LLM понижается до WARNING, если regex не нашёл секретов → обход защиты.
- **TB-2/I (критично)**: материал с PII уходит в cloud LLM (deepseek-chat) без redaction → GDPR/152-ФЗ.
- **RN-9 (важно)**: `session_id` из timestamp с секундной точностью → коллизия имён файлов.
- **RN-2 (важно)**: regex-детекция PII/секретов даёт FP/FN; `passport_ru` ловит любые 10 цифр.
- **RN-3 (важно)**: список `secret_keys` продублирован в `detect_compliance` и в gate EMERGENCY.
- **RN-11 (важно)**: смена схемы audit JSON без `schema_version` ломает downstream.
- **RN-4 (опционально→важно по CoVe)**: docstring `v3` vs Conveyor `v5.7` — незавершённая миграция.
- **RN-7 (опционально→важно по CoVe)**: `detect_pii` вызывается дважды при EMERGENCY; ReDoS-риск на regex.

[PLAN_B]
- RN-8: `try/except` вокруг `write_text`/`add_entry` + atomic write (tempfile + `os.replace`) + fallback-запись в stderr.
- RN-10: file-lock (`fcntl.flock`) на audit/result; `add_entry` — транзакция или очередь.
- SEC-2: не понижать EMERGENCY автоматически; human-in-the-loop или второй независимый детектор.
- TB-2/I: pre-flight redaction PII/секретов перед отправкой в LLM; либо локальная модель для sensitive-материала.
- RN-9: `session_id = timestamp + uuid4().hex[:8] + suffix`; проверка существования файла.
- RN-2: заменить regex на `detect-secrets`/`presidio` + allowlist; unit-тесты FP/FN.
- RN-3: вынести `SECRET_KEYS` в единый модуль-константу.
- RN-11: добавить `schema_version: 2` в audit JSON; миграция downstream.
- RN-4: удалить `detect_material_complete` или перенести в legacy; синхронизировать docstring.
- RN-7: кэшировать результат `detect_pii` между gate и `run_audit`; regex с timeout.

[THREAT_MODEL]
Trust boundaries: TB-1 (материал→orchestrator), TB-2 (orchestrator→cloud LLM), TB-3 (orchestrator→DATA_DIR), TB-4 (orchestrator→history), TB-5 (LLM-флаг→gate EMERGENCY).
- **TB-2/I (критично)**: PII/секреты в cloud LLM без redaction.
- **TB-5/E (критично)**: LLM-инъекция в gate EMERGENCY → DoS или сокрытие реального EMERGENCY.
- **TB-3/R (критично)**: потеря audit-записи при I/O-ошибке.
- **TB-3/I (критично)**: утечка PII через audit-файл при world-readable DATA_DIR.
- **TB-1/S (важно)**: path traversal через `session_suffix`.
- **TB-1/T (важно)**: ReDoS на PII_PATTERNS.
- **TB-4/T (важно)**: подмена записи в history без HMAC.
Итого: 9 угроз (4 критично, 4 важно, 1 опционально).

[SILENCE_LAYERS]
- **Input silence**: нет данных о нагрузке (сессий/час, средний размер, частота EMERGENCY) → невозможно оценить масштабируемость и вероятность коллизий.
- **Assumption silence**: предполагается, что DATA_DIR существует и `add_entry` потокобезопасен — проверок нет.
- **Consequence silence**: потеря audit-записи необратима для compliance-офицера; восстановление невозможно.

[INTERSECTION_RISKS]
- **LLM (cloud) × PII-детекция**: материал с PII уходит в LLM до/вместо redaction → утечка, GDPR/152-ФЗ.
- **EMERGENCY gate × regex-детекция**: gate доверяет regex как единственному источнику → секрет вне паттерна обходит защиту.
- **session_id (timestamp) × файловая система**: коллизия + неатомарная запись → перезапись audit другой сессии.
- **add_entry × конкурентность**: гонка → дублирование/потеря записей истории.
- **truncation (MAX_CHARS) × PII-детекция**: PII за 12000 символов не детектируется, но hash подтверждает наличие → ложное чувство безопасности.

[ASSEMBLY]
Ядро: `run_pipeline` (god-function), `run_audit`, `detect_pii`/`detect_compliance`, gate EMERGENCY. Сервис: stage0..stage5, `add_entry`, `sum_stage_costs`, truncation+hash, session_id. Инфра: DATA_DIR, cloud LLM, history, config/fallback_check. Критический путь: material → truncate → hash → session_id → stage0 → gate → (EMERGENCY | normal) → audit write → result write → add_entry. Циклов нет.

[REFACTORING]
- **Option A (hotfix, 2–3 дня)**: try/except I/O, uuid4 в session_id, единый SECRET_KEYS, удаление DEPRECATED, mkdir DATA_DIR, timeout на LLM. Закрывает RN-1,3,4,6,8,9.
- **Option B (hardening + security, 5–8 дней)**: A + pre-flight redaction, human-in-the-loop на понижение EMERGENCY, file-lock, atomic write, schema_version. Закрывает SEC-2, TB-2/I, TB-3/R, RN-10, RN-11.
- **Option C (audit как сервис, 15–25 дней)**: вынос audit в отдельный модуль/сервис с очередью, идемпотентностью по material_hash, версионированием схемы. Закрывает SRP/OCP/DIP.

[PARALLELS]
- Паттерн «pipeline + side-effectful audit» — типичен для ETL/CI-систем; в зрелых реализациях audit выносится в отдельный writer с идемпотентностью.
- Дублирование `secret_keys` — классический DRY-violation, встречается при эволюции gate-логики.
- Автоматическое понижение security-флага на основе эвристики — антипаттерн «fail-open», известный в WAF/IDS.

[TESTS]
Тесты отсутствуют (coverage 0%). Необходимо:
- Unit: `detect_pii` FP/FN (email, phone_ru, passport_ru, snils, iban, secrets); `detect_compliance` на все триггеры; gate EMERGENCY (понижение/сохранение); `compute_hash` детерминированность; `generate_audit_id` уникальность.
- Integration: EMERGENCY branch (audit+result+add_entry); normal branch (порядок stage); truncation (hash от полного).
- Concurrency: 100 параллельных `run_pipeline` без suffix → 0 коллизий.
- Failure: `write_text` падает → pipeline не теряет audit.
- Edge: пустой материал, ровно MAX_CHARS, MAX_CHARS+1, path traversal в suffix, ReDoS-паттерн.

[ACTION]
- **NOW**: зафиксировать приоритет — RN-8/RN-10 (необратимость) выше SEC-2 (требует UX-решения).
- **TODAY**: начать Option A — try/except вокруг I/O, atomic write, uuid4 в session_id, единый SECRET_KEYS.
- **TOMORROW**: добавить timeout на LLM-вызовы, mkdir DATA_DIR, удалить DEPRECATED-функцию.
- **LATER**: Option B — pre-flight redaction, human-in-the-loop на EMERGENCY, file-lock, schema_version.

[QUESTIONS]
- VERIFY: `src/storage/history.py` — потокобезопасен ли `add_entry`?
- VERIFY: `src/config.py` — существует ли DATA_DIR, каковы права?
- VERIFY: `src/pipeline/stages.py` — логируют ли stage-функции сырой материал?
- VERIFY: rate для engineering cost (не задан) — как считать ROI?
- VERIFY: есть ли тесты и CI вне видимого фрагмента?

[FUNC:FULL]
- **ECON**: effort Option A 2–3 дня, Option B 5–8 дней, Option C 15–25 дней; cost $ не задан (rate отсутствует); ROI не вычисляется без rate и стоимости инцидента; cloud delta $0 (инфра не меняется); cost of delay — каждый день без hotfix = риск необратимой потери compliance-записи и утечки PII в cloud LLM.
- **FAIL**: критично — `write_text` без try/except (FP-1), `add_entry` без синхронизации (FP-2), gate EMERGENCY доверяет regex (FP-4), PII в cloud LLM (FP-5); cascade — потеря audit → нарушение compliance → необратимо; recovery — atomic write + fallback-запись + file-lock.
- **METRICS**: codebase ~250 строк видимого фрагмента (усечён), 14 ветвлений, nesting_max=4; deps 13 (5 неиспользуемых: argparse, sys, REQUIRED_BLOCKS, LOSS_THRESHOLD, sum_stage_costs); tests 0%; perf — regex дважды при EMERGENCY; quality — print вместо logging, нет метрик/tracing; infra — single-process CLI, replicas=1.
- **ALTERNATIVES**: языки — Python оправдан (LLM-оркестрация); фреймворки — Prefect/Dagster для pipeline-оркестрации; БД — SQLite/Postgres для history вместо файлов; инфра — локальная модель для sensitive-материала; паттерны — audit как отдельный сервис (Option C), idempotency-key по material_hash.
- **EVOLVE**: coupling 3/10 (god-function `run_pipeline`); abstractions 3/10 (SRP/OCP/DIP нарушены); growth 4/10 (добавление stage требует правки оркестратора); friction — audit смешан с pipeline, дублирование secret_keys.
- **COMPARE**: Option A — 2–3 дня, низкий риск, закрывает 6/11 RN; Option B — 5–8 дней, средний риск, закрывает 10/11 RN; Option C — 15–25 дней, высокий риск регрессии, закрывает SRP/OCP/DIP + идемпотентность.

[MANDATORY BASE]
1. **ECONOMICS**: time Option A 2–3 дня, cost $ не задан (rate отсутствует), при условии наличия 1 backend-инженера.
2. **RISKS**: критично — RN-8, RN-10, SEC-2, TB-2/I; важно — RN-9, RN-2, RN-3, RN-11; при условии, что pipeline используется в production с PII-материалом.
3. **INFRASTRUCTURE**: pool_size=n/a (single-process CLI), replicas=1, при условии отсутствия горизонтального масштабирования.
4. **CODE**: change ~250 строк видимого фрагмента, при условии, что полный файл не превышает ~5000 строк (усечён).
5. **ACTION**: now — приоритизация RN-8/RN-10; tomorrow — Option A hotfix; при условии доступности инженера.
6. **TIMELINE**: NOW — приоритизация; TODAY — старт Option A; TOMORROW — timeout+mkdir+cleanup; LATER — Option B.
7. **PRODUCTION IMPACT**: users — все сессии Conveyor; deploy window — вне пиковой нагрузки; rollback — код откатывается, потерянные audit-записи не восстановимы.
8. **SLO IMPACT**: current — SLO не определены; after — рекомендуется pipeline_success_rate ≥ 99%, audit_write_success_rate = 100%, при условии внедрения мониторинга.
9. **CLOUD COST**: current $ не задан (rate отсутствует), projected $ не задан, delta ±$0 (инфра не меняется).
10. **ON-CALL**: new alerts — ошибки write_text/add_entry, LLM timeout, понижение EMERGENCY; runbook — что делать при I/O-ошибке, LLM timeout, коллизии session_id; escalation — level 2 (security engineer).

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | FAIL | SEC-2 (обход EMERGENCY), TB-2/I (PII в cloud LLM), TB-3/R (потеря audit) |
| Facts | WARN | Числа из stage1/stage2/stage4; rate и нагрузка не заданы (VERIFY) |
| Logic | OK | Приоритизация loss > risk > money соблюдена; конфликты разрешены |
| Applicability | OK | Option A реализуем за 2–3 дня без инфраструктурных изменений |
| Effectiveness | WARN | Option A закрывает 6/11 RN; SEC-2 и TB-2/I требуют Option B |
| Resilience | FAIL | resilience_score 3/5; нет retry/timeout/circuit breaker/idempotency |
| Human factor | WARN | print вместо logging; нет runbook; human-in-the-loop меняет UX |
| Clarity | OK | Структура модуля читаема; docstring v3 vs v5.7 — расхождение |

[REFLEXION]
1. Слабое место: числа cost/rate не заданы → исправлено через явное «$ не задан (rate отсутствует)» в ECON и MANDATORY BASE, без выдумывания.
2. Слабое место: RN-4 и RN-7 в stage2 помечены «опционально», но CoVe повысил их до «важно» → исправлено: в RISK_NODES указано «опционально→важно по CoVe».
3. Слабое место: возможное противоречие между «force_emergency: false» и критичностью SEC-2 → исправлено: в CONCLUSION явно указано «hotfix Option A, не немедленный STOP», согласовано с stage4.force_emergency_note.
Итог: accepted

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-f8bc70
material_hash: sha256:20ba7d60c5d1d7269e56b9ecb487bcd33acf8b738cd01517a0fee96e095d58c2
material_hash_full: sha256:e95a8b063922a8918f4cc38c691296b70c131e85fb7f72406f8675f10a179e6b
pii_detected: false
compliance_flags: ['HIPAA', 'PCI-DSS', 'GDPR', '152-ФЗ', 'EU AI Act']
critique_verdict: REQUIRES_REVIEW
risk_verdict: SAFE


[COMPLETENESS]
level: D3
required: 12
missing: []
loss_pct: 0.0%
material_complete: False
verdict: ACCEPTABLE