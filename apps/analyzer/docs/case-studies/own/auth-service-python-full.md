# auth-service-python: FULL REPORT

**Полный отчёт pipeline Vishap V5.8.**

---

## Metadata

| Field | Value |
|-------|-------|
| **Session** | `sess-2026-10-12-101603` |
| **audit_id** | `audit-2026-10-12-a6b31c` |
| **material_hash** | `sha256:22eb5cb50542fd293ec60382350f4448b83ad92f0cacceb2660152f5dc2dbf97` |
| **material_hash_full** | `sha256:22eb5cb50542fd293ec60382350f4448b83ad92f0cacceb2660152f5dc2dbf97` (original, before truncation) |
| **truncated** | `False` (original_size: 1030) |
| **Level** | `D2` |
| **task_type** | `review` |
| **Cost** | `$0.005673` |
| **Verdict** | `SAFE` |
| **Risk verdict** | `EMERGENCY` |
| **pii_detected** | `False` |
| **Compliance** | `none` |

---

## Full Vishap Output (final_markdown)

# Auth Service Review — D2

[ECHO] `auth_service.py` (~35 строк): `check_password` (SQLi через f-string, MD5, `==`-сравнение), `reset_password` (без авторизации, без rate limit, MD5). Комментарии BUG 1/2/3 корректны, но код их не устраняет. task_type=review, EMERGENCY_INTERRUPT.

[ROUTE] stage0 → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). research_first=false, parallel_stages=false, subst_count=0.

[CONCLUSION] Три критических дефекта в auth-пути: SQL injection (SEC-1, FP-1 — точка невозврата), отсутствие авторизации в `reset_password` (SEC-4 — account takeover), MD5 без соли (SEC-2 — offline crack). Система функциональна в happy-path, но не выдерживает ни одного реалистичного threat-сценария. resilience_score=2/10. Рекомендуется Option B (security-first rewrite) с dual-verify миграцией. Нет признаков наличия бэкапов users.db и их защиты (VERIFY: не проверено). Нет признаков auth-слоя выше `reset_password` (VERIFY: вызывающий код не предоставлен).

[RISK_NODES]
- RN-1 (критично): username из недоверенного источника, валидации нет.
- RN-2 (важно): MD5 обобщён как «хеш пароля» — не password-hashing функция.
- RN-3 (важно): `check_password`/`reset_password` — разные пути без общей абстракции.
- RN-4 (важно): docstring «authentication service» vs отсутствие аутентификации.
- RN-5 (важно): комментарии BUG 1/2/3 маркируют, но не исправляют.
- RN-6 (критично): `reset_password` не проверяет вызывающего — account takeover.
- RN-7 (опционально): новое соединение SQLite на каждый вызов.
- RN-8 (важно): `conn.close()` вне `finally` — утечка при исключении.
- RN-9 (важно, повышен из опционально): SQLite single-writer → критично при multi-instance.
- RN-10 (важно): конкурентный reset || check, SQLite locking не адресуется.
- RN-11 (важно): MD5 → argon2id сломает все хеши без dual-verify.

[PLAN_B]
- SEC-1: параметризованные запросы (`cursor.execute(..., (username,))`)
- SEC-2: argon2id + dual-verify миграция (флаг `algo` в схеме)
- SEC-3: `hmac.compare_digest` вместо `==`
- SEC-4: обязательный `actor` в `reset_password` + авторизация (fail-closed)
- SEC-5: rate limit по username+IP, lockout после N неудач
- SEC-6: валидация username (regex) и пароля (длина ≥ 12, Unicode NFC)
- SEC-7: проверять `cursor.rowcount`, возвращать явный результат
- RN-8: `with closing(sqlite3.connect(...))` + `try/except sqlite3.Error`
- RN-10: транзакционная изоляция + retry на `database is locked`
- RN-11: dual-verify без принудительного сброса
- FP-4: закрытие соединения в `finally` / context manager
- FP-6: явный результат `reset_password` (bool/exception)

[ASSEMBLY] Иерархия плоская: core (`check_password`, `reset_password`) → service (`users.db`, caller) → infra (filesystem, stdlib). Нет слоя абстракции между auth-логикой и хранилищем — корень RN-3 и RN-9. Критический путь: `caller → check_password → cursor.execute(f-string) → users.db → == compare`. Циклов нет.

[REFACTORING] Phase 1 (hotfix, часы): параметризация SQL + `compare_digest` + context manager. Phase 2 (дни): argon2id + dual-verify + authz в `reset_password` + audit log. Phase 3 (follow-up): extract repository (Option C). Схема additive: `ALTER TABLE users ADD COLUMN algo TEXT NOT NULL DEFAULT 'md5'` + `password_hash_v2` + UNIQUE index на username.

[PARALLELS] Option A (minimal hotfix) — закрывает SEC-1/SEC-3 за часы, но оставляет MD5 и no-auth reset. Option B (security-first rewrite) — закрывает SEC-1..SEC-7, рекомендуется. Option C (extract repository + B) — устраняет корень RN-3/RN-9, но 3–5 дней, избыточно для EMERGENCY-окна.

[TESTS] 0% coverage. Нужны: regression на `username="' OR '1'='1"` → False (SEC-1); regression на `reset_password` без actor → raises (SEC-4); timing-тест на `compare_digest` (SEC-3); integration dual-verify миграции; integration конкурентный reset+check (SQLite locking); property: любой username не меняет семантику SQL. Edge cases: пустой username, Unicode/эмодзи, пароль 0 и 10^6, несуществующий username (rowcount=0).

[ACTION]
- NOW: остановить деплой auth-пути; параметризовать SQL в `check_password` (SEC-1, FP-1); заменить `==` на `hmac.compare_digest` (SEC-3).
- TODAY: ввести обязательный `actor` в `reset_password` (SEC-4, fail-closed); обернуть connect в context manager (RN-8/FP-4); добавить валидацию username/password (SEC-6).
- TOMORROW: argon2id + dual-verify миграция (SEC-2/RN-11); rate limit + lockout (SEC-5); audit log (STRIDE R).
- LATER: extract repository (Option C, RN-3/RN-9); миграция SQLite → Postgres при `database is locked` > 1%.

[QUESTIONS]
- VERIFY: есть ли бэкапы `users.db` и шифрованы ли они? (если нет — SEC-2 необратимо-критично)
- VERIFY: кто вызывает `reset_password` — есть ли auth-слой выше? (влияет на форму SEC-4 fix)
- VERIFY: допустима ли `argon2-cffi` как внешняя зависимость? (иначе — `hashlib.scrypt` stdlib)
- VERIFY: single-instance или multi-instance деплой? (RN-9: при multi-instance → критично)

[FUNC:FULL]
- ECON: effort Option A ~0.5–1 день, Option B ~2–3 дня, Option C ~3–5 дней (rate не задан); cost $ не вычисляется без rate; ROI положительный при любом rate (предотвращает account takeover всех пользователей); cost_of_delay — каждый день окно для takeover, утечка MD5 необратима.
- FAIL: критично FP-1 `cursor.execute(f-string)` (SQLi, точка невозврата), FP-2 `reset_password` без authz (takeover), FP-3 `hashlib.md5` (offline crack); cascade: SQLi → выгрузка хешей → offline crack → password reuse → компромисс других сервисов; recovery: откат кода возможен, утечка хешей — нет (принудительный сброс паролей).
- METRICS: ~35 строк, 2 функции, 0 классов, 2 deps (hashlib, sqlite3 stdlib), 0 тестов (0% coverage), perf не измерена, quality — нарушены OWASP A03/A02 + PEP 249, infra — SQLite single-writer, нет пула/timeout/health-checks.
- ALTERNATIVES: языки — N/A (Python зафиксирован); фреймворки — N/A; БД — SQLite (текущая) vs Postgres (Option C, multi-writer); инфра — single-instance vs multi-instance; паттерны — inline SQL vs UserRepository (DIP); хеширование — MD5 (текущее) vs argon2id (рекомендуется) vs scrypt (stdlib fallback).
- EVOLVE: coupling 2/10 (жёсткая привязка к sqlite3 и MD5), abstractions 1/10 (нет слоя над хранилищем), growth 2/10 (любая смена алгоритма/хранилища — breaking change), friction 3/10 (feature_add), overall 2/10.
- COMPARE: Option A — time 0.5–1д, cost низкий, risk средний (MD5+no-auth остаются), complexity низкая; Option B — time 2–3д, cost средний, risk низкий, complexity средняя; Option C — time 3–5д, cost высокий, risk низкий, complexity высокая.

[MANDATORY BASE]
1. ECONOMICS: time Option B ~2–3 дня, cost $ не вычисляется (rate не задан), при условии наличия 1 backend-инженера; cost_of_delay — необратимое окно takeover.
2. RISKS: критично SEC-1 (SQLi), SEC-4 (no-auth reset), SEC-2 (MD5); важно SEC-3 (timing), SEC-5 (no rate limit), SEC-6 (no validation), RN-8 (leak), RN-10 (concurrency), RN-11 (migration); при условии, что caller недоверенный (RN-1).
3. INFRASTRUCTURE: pool_size=N/A (SQLite single-writer), при условии Option C → pool_size ≥ 5 (Postgres); timeout рекомендуется 5.0s (сейчас отсутствует); replicas=1.
4. CODE: change ~35 строк → ~120 строк (Option B), при условии сохранения публичных сигнатур кроме `reset_password` (+actor).
5. ACTION: now — параметризация SQL + compare_digest; tomorrow — argon2id + dual-verify + authz + audit log.
6. TIMELINE: NOW — stop deploy, SEC-1/SEC-3 fix; TODAY — SEC-4/SEC-6/RN-8; TOMORROW — SEC-2/RN-11/SEC-5/audit; LATER — Option C, Postgres migration.
7. PRODUCTION IMPACT: users N (не задано в материале), deploy window — Phase 1 hotfix часы, rollback Phase 1 — минуты (код), rollback Phase 2 — не требуется (схема additive).
8. SLO IMPACT: current — SLO не определены (defined=false); after — предложено check_password p99 < 50ms, reset success rate > 99.9%, login_failure_rate alert > 5%/5мин, при условии внедрения метрик.
9. CLOUD COST: current $N (не задано), projected $N (не задано), delta ±$0 — no infrastructure change (Option B меняет только код и схему).
10. ON-CALL: new alerts — login_failure_rate > 5%/5мин, reset без actor > 0, доля md5-хешей > 10% через 30 дней, `database is locked` > 1%; runbook — «database is locked» + подозрение на SQLi/брутфорс; escalation — security engineer при срабатывании SEC-алертов.

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | FAIL | SQLi (SEC-1), MD5 (SEC-2), timing (SEC-3), no-auth reset (SEC-4), no rate limit (SEC-5) |
| Facts | OK | Все findings подтверждены кодом; числа не выдуманы (rate/pool_size помечены N/A) |
| Logic | OK | Приоритеты согласованы: SEC-1 > SEC-4 > SEC-2; конфликты разрешены в stage4.collision |
| Applicability | WARN | Option B требует argon2-cffi (VERIFY) или scrypt fallback; breaking change API reset_password |
| Effectiveness | OK | Option B закрывает SEC-1..SEC-7; Phase 1 закрывает SEC-1/SEC-3 за часы |
| Resilience | FAIL | resilience_score=2/10; нет timeout, circuit breaker, retry, audit log, тестов |
| Human factor | WARN | Комментарии BUG 1/2/3 корректны, но не исправлены — риск «маркер вместо фикса» |
| Clarity | OK | Дефекты локализованы, номера строк/функций указаны, fix-ы конкретны |

[REFLEXION]
1. Слабое место: числа (rate, pool_size, users N) не заданы в материале → исправлено: помечены N/A / «не задано», не выдуманы.
2. Слабое место: риск, что Option B требует внешней зависимости argon2-cffi, конфликтует с «нет внешних deps» → исправлено: указан scrypt (stdlib) как fallback + VERIFY.
3. Слабое место: RN-9 был опционально в stage2, но при multi-instance становится критично → исправлено: повышен до «важно» с условием multi-instance (VERIFY).
Итог: accepted

[CHANGELOG]
| # | What changed | Reason |
|---|--------------|--------|
| 1 | RN-9: опционально → важно | Risk High (multi-instance → критично) |
| 2 | reset_password: добавлен обязательный actor | Risk High (SEC-4 account takeover) |
| 3 | MD5 → argon2id + dual-verify | Risk High (SEC-2 необратимо) |
| 4 | `==` → `hmac.compare_digest` | Risk Medium (SEC-3 timing) |
| 5 | f-string SQL → параметризация | Risk High (SEC-1 SQLi) |

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-a6b31c
material_hash: sha256:22eb5cb50542fd293ec60382350f4448b83ad92f0cacceb2660152f5dc2dbf97
material_hash_full: sha256:22eb5cb50542fd293ec60382350f4448b83ad92f0cacceb2660152f5dc2dbf97
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
- `final_markdown` length: 10511 chars.
- Source JSON: `data/result_sess-*.json` (in `.gitignore` — this file is the public copy).
- Short version: [auth-service-python.md](auth-service-python.md)
