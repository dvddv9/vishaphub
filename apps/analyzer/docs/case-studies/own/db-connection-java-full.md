# db-connection-java: FULL REPORT

**Полный отчёт pipeline Vishap V5.8.**

---

## Metadata

| Field | Value |
|-------|-------|
| **Session** | `sess-2026-10-12-101851` |
| **audit_id** | `audit-2026-10-12-3c8bf3` |
| **material_hash** | `sha256:5975e359de0b86c12a96b34411e18193c4da6ba8ea6bf60ae048ca45f3894a25` |
| **material_hash_full** | `sha256:5975e359de0b86c12a96b34411e18193c4da6ba8ea6bf60ae048ca45f3894a25` (original, before truncation) |
| **truncated** | `False` (original_size: 1363) |
| **Level** | `D2` |
| **task_type** | `review` |
| **Cost** | `$0.005815` |
| **Verdict** | `SAFE` |
| **Risk verdict** | `EMERGENCY` |
| **pii_detected** | `False` |
| **Compliance** | `none` |

---

## Full Vishap Output (final_markdown)

# DbConnection — Code Review (D2, EMERGENCY)

[ECHO] Java-класс `DbConnection` (~40 LOC, 4 метода): `getUser`, `bulkInsert`, `queryUnsafe`, `init`. Материал: JDBC-доступ к PostgreSQL без pool, без resource management, с hardcoded credentials. task_type=review, level=D2, session=sess-2026-10-12-XXXXXX.

[ROUTE] stage0 → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). research_first=false, parallel_stages=false, subst_count=0. Flags: EMERGENCY_INTERRUPT.

[CONCLUSION] Класс в prod-пути содержит 3 критичных уязвимости (SQL injection ×2, hardcoded credentials) и 3 критичных дефекта надёжности (connection leak, thread-unsafe shared Connection, отсутствие pool). Рекомендуется Option B (HikariCP + try-with-resources + параметризация). Ротация пароля — сегодня, независимо от рефакторинга. Признаков CI/CD, тестов, observability не найдено (VERIFY: не проверялось вне материала).

[RISK_NODES]
- RN-1 (критично): допущение о валидности `user`/`pass`/localhost во всех средах — нет env/secret store.
- RN-6 (критично): системное избегание resource/error management (нет try-with-resources, pool, timeout, transaction, логирования).
- RN-8 (критично): утечка Connection/Statement/ResultSet на success и exception путях; bulkInsert без транзакции → частичные записи.
- RN-9 (критично): нет pool → исчерпание `max_connections` Postgres → отказ сервиса.
- RN-10 (критично): `shared` Connection без синхронизации; JDBC не thread-safe; `init()` не volatile, не идемпотентен.
- RN-11 (важно): `queryUnsafe` возвращает live ResultSet на shared Connection — любой фикс ломает контракт вызывающих.
- RN-7 (важно): bulkInsert без batch → N round-trips; getUser открывает соединение на каждый вызов.
- RN-5 (важно): `import java.util.concurrent.*` не используется, при этом shared Connection требует синхронизации.
- RN-2 (важно): нет валидации входа (`id`, `sql`, `names`).
- RN-3 (важно): три конкурирующие lifecycle-стратегии получения Connection.
- RN-4 (опционально): комментарии «BUG 1/2/3» позиционируют код как учебный, но класс назван `DbConnection` с prod-URL.

[PLAN_B]
- SEC-1: `PreparedStatement` с параметром `?` вместо конкатенации `id`.
- SEC-2: удалить `queryUnsafe` (backdoor) или заменить allowlist параметризованных методов.
- SEC-3/SECRET-1: вынести credentials в env/secret manager + немедленная ротация пароля.
- SEC-4/RN-9: HikariCP с лимитом соединений и connection timeout.
- SEC-5: санитизация/маппинг SQLException на границе.
- RN-8/FP-1: try-with-resources для Connection/Statement/ResultSet во всех методах.
- RN-10/FP-3: убрать shared Connection; connection-per-call из pool.
- RN-8/FP-4: batch + явная транзакция с rollback в bulkInsert.
- FP-6: `setQueryTimeout` + connection timeout.
- RN-11/BC-1: миграция queryUnsafe через deprecation-фазу с параллельным API (или немедленное удаление — см. second_opinion).
- Observability: структурное логирование + метрики pool/ошибок.

[ASSEMBLY] Единственный класс `DbConnection` совмещает: lifecycle соединения (`init`), read (`getUser`), write (`bulkInsert`), raw query (`queryUnsafe`). Нет service/domain слоя. Callers `queryUnsafe` — неявный сервисный слой, владеющий ResultSet lifecycle. Критический путь: `caller → queryUnsafe → shared Connection → PostgreSQL → ResultSet → caller (unbounded lifetime)`.

[REFACTORING] Option B (рекомендуемый): HikariCP DataSource, try-with-resources, PreparedStatement, batch+transaction в bulkInsert, удаление shared Connection, queryUnsafe → deprecation + allowlist API, credentials через env. Фазы: Phase 0 (сегодня) — ротация пароля + env; Phase 1 (день 1) — try-with-resources + PreparedStatement в getUser; Phase 2 (день 1–2) — HikariCP + удаление shared; Phase 3 (день 2–3) — batch+transaction, deprecation queryUnsafe; Phase 4 (день 3+) — удаление queryUnsafe.

[PARALLELS] Option A (minimal hotfix, без pool) — быстрый rollback, но не решает RN-9/RN-10. Option C (Repository + Service Layer) — устраняет SOLID-нарушения, но overkill для ~40 LOC и требует одновременного изменения всех вызывающих. Option B — баланс: устраняет RN-8/RN-9/RN-10/FP-1..FP-7, ценой BC-1/BC-2.

[TESTS] Coverage 0%. Необходимо: unit — `getUser` с `id='1 OR 1=1'` не возвращает чужие строки; unit — сбой на 3-й строке bulkInsert → 0 записей; concurrency — 100 параллельных вызовов без ошибок; resource — connection count не растёт после N вызовов; integration — pool limit соблюдается; integration — timeout на зависший запрос. Edge cases: id не существует → null; names = null/empty; SQLException в середине bulkInsert; параллельный init().

[ACTION]
- NOW: ротация пароля БД (необратимо скомпрометирован — уже в VCS); вынос credentials в env/secret manager; остановка деплоя до фикса SEC-1/SEC-2.
- TODAY: try-with-resources + PreparedStatement в `getUser`; удаление/блокировка `queryUnsafe`.
- TOMORROW: HikariCP DataSource + удаление shared Connection; batch+transaction в `bulkInsert`.
- LATER: миграция вызывающих `queryUnsafe`; observability (логирование, метрики pool); SLO/алерты/runbook.

[QUESTIONS]
1. Вызывается ли `queryUnsafe` из HTTP-слоя с пользовательским вводом? (VERIFY: не проверено — критично для оценки blast radius)
2. Каков RPS и типичный размер `names[]`? (VERIFY: input_silence — pool_size недоказуем)
3. Каков `max_connections` Postgres и число инстансов сервиса? (VERIFY: C1 не проверен)
4. Кто владелец БД и возможна ли ротация пароля сегодня? (VERIFY: вне контроля кода)
5. Есть ли CI/CD, сканер секретов, staging? (VERIFY: не evidenced в материале)

[FUNC:FULL]
- ECON: effort ~2–3 дня (Option B), cost $0 cloud delta (HikariCP — in-process), ROI не вычисляется без rate; cost of delay — качественно: каждый день = риск SQL injection + исчерпание соединений в prod.
- FAIL: критично — SQL injection (getUser, queryUnsafe), hardcoded credentials, thread-unsafe shared Connection, connection leak; cascade — исчерпание max_connections → отказ всего сервиса; recovery — рестарт БД + ротация пароля (необратимо).
- METRICS: ~40 LOC, 4 метода, 2 deps (java.sql, java.util.concurrent — unused), 0 tests, 0% coverage, observability = none, SLO не заданы, resilience_score = 1/10.
- ALTERNATIVES: Option A (minimal hotfix, без pool) / Option B (HikariCP + DataSource, рекомендуемый) / Option C (Repository + Service Layer, стратегический); альтернативы БД/языка не рассматриваются — материал фиксирован на Java+PostgreSQL.
- EVOLVE: coupling = 2/10 (hardcoded URL/credentials, нет DataSource-абстракции), abstractions = 1/10, feature_add = 2/10, module_replace = 2/10; live ResultSet-контракт блокирует рефакторинг (RN-11).
- COMPARE: Option A — 0.5–1 день, низкий риск, не решает RN-9/RN-10; Option B — 2–3 дня, средний риск (BC-1/BC-2), устраняет все критичные; Option C — дни, высокий риск миграции, overkill для ~40 LOC.

[MANDATORY BASE]
1. ECONOMICS: time 2–3 дня (Option B), cost $0 cloud delta, при условии отсутствия данных о rate и потерях от инцидентов — ROI не вычисляется.
2. RISKS: критично — SEC-1/SEC-2 (SQL injection), SEC-3/SECRET-1 (credentials), RN-8/RN-9/RN-10 (leak/pool/concurrency); важно — RN-7/RN-11/FP-4/FP-6; при условии, что queryUnsafe вызывается недоверенным кодом — blast radius = вся БД.
3. INFRASTRUCTURE: pool_size рекомендован 10–20 (HikariCP default 10), при условии неизвестного RPS и max_connections Postgres — точное значение недоказуемо (input_silence).
4. CODE: change ~40 LOC переписать (Option B), при условии сохранения сигнатур getUser/bulkInsert; queryUnsafe — breaking change (BC-1).
5. ACTION: now — ротация пароля + env + stop deploy; tomorrow — HikariCP + удаление shared Connection.
6. TIMELINE: NOW — ротация пароля, env, stop deploy; TODAY — try-with-resources + PreparedStatement в getUser; TOMORROW — HikariCP + удаление shared; LATER — миграция queryUnsafe, observability, SLO.
7. PRODUCTION IMPACT: users N (не задано материалом), deploy window — внеплановый hotfix, rollback — откат кода не устраняет утечку credentials (требуется ротация).
8. SLO IMPACT: current — SLO не заданы (defined=false), after — не измеримо без метрик; при условии введения SLO — latency p99 < 500ms, error rate < 1%.
9. CLOUD COST: current $0, projected $0, delta ±$0 — HikariCP in-process, cloud-ресурсы не создаются.
10. ON-CALL: new alerts — connection_count_active > 80% pool_size, sql_exception_rate > 1%, bulkInsert_partial_writes > 0; runbook — отсутствует (создать); escalation — владелец БД для ротации пароля.

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | FAIL | SQL injection ×2, hardcoded credentials, thread-unsafe shared Connection |
| Facts | OK | Все findings привязаны к строкам исходника; числа с условиями |
| Logic | OK | Причинно-следственные связи (leak → исчерпание → DoS) обоснованы |
| Applicability | WARN | Option B применим, но требует данных о нагрузке и вызывающих queryUnsafe |
| Effectiveness | WARN | Фиксы устраняют критичные дефекты, но BC-1/BC-2 требуют миграции |
| Resilience | FAIL | resilience_score = 1/10; нет pool, timeout, транзакций, observability |
| Human factor | WARN | Комментарии «BUG 1/2/3» маскируют prod-код; нет runbook |
| Clarity | OK | Отчёт структурирован, приоритеты явные |

[REFLEXION]
1. Слабое место: pool_size рекомендован без данных о RPS → исправлено: значение 10–20 помечено как рекомендация по умолчанию, требует валидации (input_silence).
2. Слабое место: конфликт deprecation vs удаление queryUnsafe → исправлено: зафиксирован в [PLAN_B] и second_opinion (security engineer настаивает на немедленном удалении).
3. Слабое место: cloud_cost = 0 мог быть воспринят как «нет затрат» → исправлено: reason явно указывает «no infrastructure change, HikariCP in-process».
Итог: accepted

---

**EMERGENCY:** force_emergency=true. Действия NOW: ротация пароля БД, вынос credentials в env, остановка деплоя до фикса SEC-1/SEC-2.

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-3c8bf3
material_hash: sha256:5975e359de0b86c12a96b34411e18193c4da6ba8ea6bf60ae048ca45f3894a25
material_hash_full: sha256:5975e359de0b86c12a96b34411e18193c4da6ba8ea6bf60ae048ca45f3894a25
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
- `final_markdown` length: 10243 chars.
- Source JSON: `data/result_sess-*.json` (in `.gitignore` — this file is the public copy).
- Short version: [db-connection-java.md](db-connection-java.md)
