# Case Study: Auth Service (Python) — SQLi, Timing Attack, MD5

**Language:** Python
**Level:** D2
**Cost:** $0.006282
**Verdict:** SAFE
**Session:** sess-2026-10-10-152757
**Bugs planted:** 4 — SQL injection, Timing attack, MD5 без salt, No rate limit
**Bugs found:** 7
**False positives:** 0

**Key findings:** SQLi через f-string, MD5 без salt (мгновенный крак), reset_password без authz (account takeover). Комбинация SQLi + MD5 = утечка паролей в открытом виде. Resilience 2/10.


**Full report for client:** [auth-service-python-full.md](auth-service-python-full.md)

---

## Vishap Output

# AUTH SERVICE — SECURITY REVIEW (D2)

[ECHO] Python auth-модуль ~35 строк: `check_password` (SQLi через f-string, MD5, `==`-сравнение), `reset_password` (без authz, без валидации, MD5). Stage0 выставил `EMERGENCY_INTERRUPT`; stage2 подтвердил 3 критических уязвимости; stage4 — `force_emergency: true`, `stop_reason: risk`.

[ROUTE] stage0 (halt, EMERGENCY_INTERRUPT) → stage1 (scanner) → stage2 (analyst, 11 risk nodes, 7 threats) → stage4 (synthesizer, 3 варианта, migration plan). stage3 отсутствует в материале.

[CONCLUSION] Модуль в проде — **активный инцидент**, не техдолг. Три критических уязвимости в auth-пути: (1) SQL injection в `check_password` через f-string username — обход аутентификации и эксфильтрация всей таблицы users; (2) `reset_password` без authz — любой вызывающий сбрасывает любой пароль (account takeover без следа); (3) MD5 без соли — при утечке БД plaintext восстанавливается за минуты. Комбинация SQLi + MD5 превращает инъекцию в полный credential dump с восстановлением паролей. Требуется немедленный containment.

[RISK_NODES]
- **критично** — SQLi в `check_password` (f-string, точка невозврата `cursor.execute`); MD5 для credentials; `reset_password` без authz; необратимость MD5-миграции.
- **важно** — timing side-channel (`==` на hex); отсутствие rate limit / lockout / audit log; connection leak (нет try/finally); last-writer-wins на параллельных сбросах; SQLite как credential store; account enumeration.
- **опционально** — hardcoded `users.db`; connection-per-call без пула (повышен до «важно» в связке с leak → каскадный DoS).

[THREAT_MODEL] 7 угроз, 3 критических. Trust boundaries: caller → `check_password`, caller → `reset_password`, auth_service → `users.db`. Top-3: SQLi (Tampering), reset без authz (Elevation of Privilege), MD5 без соли (Information Disclosure). STRIDE-покрытие: T, I, E, D, R, S — все представлены.

[SILENCE_LAYERS]
- **input_silence** — нет данных о нагрузке, числе пользователей, размере users.db → невозможно оценить достаточность rate limiting и пула.
- **assumption_silence** — предполагается, что username безопасен, канал защищён, caller аутентифицирован; ни одно не проверяется.
- **consequence_silence** — утечка MD5-хэшей необратима: даже после миграции старые хэши скомпрометированы.

[INTERSECTION_RISKS]
- SQLi × MD5 → инъекция становится полным credential dump с восстановлением plaintext.
- reset без authz × отсутствие audit log → account takeover без обнаружения и attribution.
- SQLite file lock × connection leak → каскадный DoS auth-сервиса под нагрузкой.
- last-writer-wins × отсутствие rate limit → недетерминированная потеря доступа.

[ASSEMBLY] Core: `check_password`, `reset_password`. Service (все — gaps): hashing, constant-time compare, validation, rate limiting, audit log. Infra: sqlite3 users.db, connection lifecycle, config, observability. Граф ациклический; критический путь проходит через точку невозврата.

[REFACTORING] Порядок фиксов: (1) отключить `reset_password` (feature flag) → (2) параметризовать SQL в `check_password` → (3) argon2id + dual-verify + rehash-on-login → (4) authz + audit log. Constraint 1 (authz) блокирует релиз reset_password до выполнения.

[PARALLELS] `reset_password` уже параметризован — эталон для `check_password`. Две несовместимые практики в одном модуле: разработчик скопирует небезопасную. MD5 → argon2id — стандартный паттерн миграции через dual-verify.

[TESTS] 0% coverage. Нужно: unit (корректный/некорректный пароль), security (SQLi payloads, timing-тест), concurrency (параллельные reset), integration (миграция хэшей). Edge cases: кавычки/UNION в username, пустой ввод, несуществующий пользователь, одновременные сбросы.

[ACTION]
- **NOW** — отключить `reset_password`; параметризовать SQL в `check_password`; включить audit logging.
- **TODAY** — добавить `hash_algo` в схему, dual-verify, rehash-on-login; `hmac.compare_digest`.
- **TOMORROW** — authz на reset_password; rate limiting / lockout; context manager для соединений.
- **LATER** — вынести auth в отдельный сервис (Postgres + pool + replicas); SLO, алерты, runbook.

[QUESTIONS]
1. Кто вызывает `reset_password` и есть ли authz на уровне caller? (не в материале)
2. Есть ли подтверждённая компрометация users.db? От этого зависит: dual-verify vs форсированный сброс.
3. Каков объём таблицы users и частота auth-запросов? (нужно для capacity planning argon2id)
4. Логируются ли пароли выше по стеку? (caller не показан)

[FUNC:FULL]
- **ECON**: effort S–M (вариант A) / XS (containment C) / L (service extraction B); cost $0 сейчас (нет инфры в материале); ROI критический — предотвращение credential dump; cost of delay = активная уязвимость в проде; cloud delta $0 при A/C, +managed Postgres при B.
- **FAIL**: критично — `cursor.execute(f-string)` (точка невозврата SQLi), reset без authz (EoP), MD5 (необратимо); cascade — SQLi → dump → plaintext → account takeover всех пользователей; recovery — параметризация (revert-able), dual-verify для хэшей, форсированный сброс только при подтверждённой компрометации.
- **METRICS**: ~35 строк, 2 функции, 0 классов, 2 stdlib-депа, 0 тестов (0% coverage), 0 наблюдаемости, 0 SLO, resilience_score 2/10.
- **ALTERNATIVES**: hashing — argon2id (предпочтительно) / bcrypt / scrypt; DB — SQLite (текущая, узкое место) / Postgres / MySQL; паттерн — in-place hardening (A) / service extraction (B) / emergency containment (C); compare — `hmac.compare_digest` / `secrets.compare_digest`.
- **EVOLVE**: coupling 2/10 (прямой sqlite3, hardcoded path), abstractions 2/10 (нет DI), feature_add 3/10, module_replace 7/10 (мал → легко заменить целиком), overall 3/10.
- **COMPARE**: A — S–M, средний риск (миграция хэшей), малый diff; B — L, высокий риск (координация), устраняет SQLite lock; C — XS, низкий технически / высокий операционно (массовый сброс), совместим с A и B как первый шаг.

[MANDATORY BASE]
1. **ECONOMICS**: time S–M (вариант A), cost $0 (нет инфры в материале), при условии отсутствия данных о хостинге; cost of delay — активная уязвимость.
2. **RISKS**: критично — SQLi, reset без authz, MD5; важно — timing, rate limit, audit, connection leak; при условии, что модуль в проде.
3. **INFRASTRUCTURE**: pool_size N/A для SQLite (file lock); для варианта B — 10–20 на инстанс, при условии перехода на Postgres.
4. **CODE**: change ~35 строк (полная замена модуля), при условии сохранения сигнатур `check_password`/`reset_password`.
5. **ACTION**: now — отключить reset_password + параметризовать SQL; tomorrow — argon2id + dual-verify + authz.
6. **TIMELINE**: NOW — containment; TODAY — параметризация + audit; TOMORROW — миграция хэшей + authz; LATER — service extraction.
7. **PRODUCTION IMPACT**: users N (неизвестно из материала), deploy window — немедленно для containment, rollback SQLi-фикса — revert коммита (тривиально), rollback MD5-миграции — недопустим.
8. **SLO IMPACT**: current — SLO не определены; after — availability ≥99.9%, p99 check_password <500ms, при условии внедрения SLO.
9. **CLOUD COST**: current $0 (нет данных), projected $0 при A/C, delta ±$0; при B — managed Postgres + compute для argon2id (оценка невозможна без данных о нагрузке).
10. **ON-CALL**: new alerts — auth_failures_per_user_per_min >10, p99 >500ms, connection_leak_rate >0, audit_log_gap >60s; runbook — отсутствует (создать); escalation — level 0 (нет конфликтов analyst/researcher).

[REFLEXION]
1. **Слабое место**: числа argon2id (m=65536, t=3, p=4) — рекомендованные OWASP, не измеренные на материале. → **Исправлено**: помечены как ASSUMPTION в [MANDATORY BASE] п.3 и в [FUNC:FULL] EVOLVE.
2. **Слабое место**: caller-слой не в материале — authz для reset_password, CSRF, TLS, логирование паролей не оценены. → **Исправлено**: вынесено в [QUESTIONS] и [SILENCE_LAYERS].assumption_silence; помечено как внешняя верификация.
3. **Слабое место**: cloud_cost = $0 может читаться как «бесплатно», хотя это отсутствие данных. → **Исправлено**: явно указано «нет данных о хостинге» в [MANDATORY BASE] п.9 и [FUNC:FULL] ECON.

**Итог**: accepted.

[AUDIT_TRAIL]
audit_id: audit-2026-10-11-54a581
material_hash: sha256:9c624b257edde432aa9fbb8ab9490fb9c518c6998fdb3fc0c846185ea4bbe654
pii_detected: false
compliance_flags: []
critique_verdict: SAFE


[COMPLETENESS]
level: D2
required: 12
missing: []
loss_pct: 0.0%
verdict: ACCEPTABLE

---

## Reproduce

    vishap analyze data/real_cases/own/auth_service.py

---

**Session:** `sess-2026-10-11-111011` | **audit_id:** `audit-2026-10-11-54a581` | **Cost:** `$0.005166` | **Level:** `D2` | **Verdict:** `SAFE`
