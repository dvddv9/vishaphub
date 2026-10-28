# Case Study: DB Connection (Java) — Connection Leak, SQLi, Hardcoded Credentials

**Language:** Java
**Level:** D2
**Cost:** $0.005200
**Verdict:** SAFE
**Session:** sess-2026-10-10-154112
**Bugs planted:** 3 — Connection leak, No timeout/pool, Thread-unsafe shared conn
**Bugs found:** 9
**False positives:** 0

**Key findings:** 5 критичных: SQLi в getUser, queryUnsafe = public backdoor, hardcoded creds user/pass, connection leaks, race на shared Connection. Conveyor заметил: комментарии маскируют SQLi и секреты. Ротация пароля — до деплоя.


**Full report for client:** [db-connection-java-full.md](db-connection-java-full.md)

---

## Vishap Output

# DbConnection.java — Security & Reliability Review

**Level:** D2 · **Session:** sess-2026-10-12-XXXXXX · **Flags:** EMERGENCY_INTERRUPT · **Route:** stage4 → stage3 (stage3 skipped, research_first=false)

---

## [ECHO]

Материал — Java-класс `DbConnection` (~40 строк, 4 публичных метода, 1 shared-поле, 1 константа). Класс смешивает две несовместимые стратегии соединений: per-call (`getUser`, `bulkInsert`) и shared-state (`init`/`queryUnsafe`). Комментарии BUG 1–3 фиксируют утечки и thread-safety, но умалчивают о SQLi и хардкод-креденшелах. `java.util.concurrent.*` импортирован, но не используется. Тестов нет, логирования нет, пула нет, таймаутов нет.

---

## [ROUTE]

stage0 → gate_check: **EMERGENCY_INTERRUPT** (SQLi + hardcoded secrets) → route halted → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → **stage5 (transmitter)**. stage3 не запускался (`research_first=false`). `subst_count=0`.

---

## [CONCLUSION]

Класс в текущем виде — **активная уязвимость в проде**, а не «код с багами». Пять критичных проблем: (1) SQL-инъекция в `getUser` через конкатенацию `id`; (2) `queryUnsafe` — публичный backdoor для произвольного SQL; (3) хардкод-креденшелы `"user"/"pass"` в исходнике; (4) утечки соединений на всех путях; (5) гонка на shared `Connection`. Плюс отсутствие пула, таймаутов, метрик, тестов. `resilience_score = 1/10`. Требуется **немедленный hotfix** (вариант A) + **целевой рефакторинг** (вариант B, DAO + HikariCP). Ротация пароля `pass` — **до** деплоя, независимо от кода.

---

## [RISK_NODES]

| # | Узел | Приоритет | Суть |
|---|------|-----------|------|
| 1 | Неявное допущение | критично | `id` предполагается внутренним int; конкатенация в SQL — уже нарушение |
| 5 | Внутреннее противоречие | критично | Класс одновременно static utility и stateful singleton — непригоден ни для одного паттерна |
| 8 | Надёжность | критично | Утечки соединений на exception-путях и на нормальном возврате `getUser` |
| 9 | Масштабируемость | критично | Нет пула/лимита/таймаута → каскадный отказ БД |
| 10 | Конкурентность | критично | `shared` Connection не thread-safe; `init()` не volatile, не идемпотентен |
| 2 | Слабое обобщение | важно | «Это просто DAO» — ложно; поведение зависит от метода |
| 3 | Конкурирующая реализация | важно | Два источника истины для соединения в одном классе |
| 4 | Сдвиг тезиса | важно (↑ из опционально) | Комментарии фокусируют на ресурсах, маскируя SQLi и секреты |
| 6 | Стратегическое избегание | важно | Отсутствие try-with-resources/пула/таймаутов/тестов — системно |
| 7 | Производительность | важно | `DriverManager.getConnection` на каждый вызов; `bulkInsert` без batch |
| 11 | Ломающие изменения | важно | `queryUnsafe` возвращает живой ResultSet — рефакторинг сломает вызывающих |

---

## [THREAT_MODEL]

**Компоненты:** DbConnection, PostgreSQL (localhost/db), Caller, источник данных для `id`/`names`/`sql`.
**Trust boundaries:** Caller → DbConnection (public API); DbConnection → PostgreSQL (JDBC); источник данных → методы.

| STRIDE | Компонент | Угроза | Приоритет | Митигация |
|--------|-----------|--------|-----------|-----------|
| T | getUser | SQLi через конкатенацию `id` | критично | PreparedStatement + валидация типа |
| E | queryUnsafe | Произвольный SQL на shared-соединении | критично | **Удалить метод** |
| S | DbConnection | Хардкод-креденшелы → спуфинг при утечке | критично | Vault/env + ротация + least-privilege |
| D | DbConnection | Утечки + нет пула/таймаута → исчерпание БД | критично | try-with-resources, HikariCP, timeouts |
| T | shared Connection | Гонка на createStatement/executeQuery | критично | Убрать shared; соединение из пула |
| R | DbConnection | Нет audit log | важно | Логирование с correlation id |
| I | getUser/bulkInsert | SQLException с параметрами в логи/ответы | важно | Санитизация сообщений |

**Итого:** 7 угроз — 5 критичных, 2 важных. **Top-3:** SQLi в `getUser` (T), произвольный SQL через `queryUnsafe` (E), утечки + отсутствие пула → DoS (D).

---

## [SILENCE_LAYERS]

- **Input silence:** нет данных о RPS, размере БД, размере `names[]`, частоте вызовов → масштаб DoS неопределён.
- **Assumption silence:** «`id` всегда int из доверенного источника» — не проверяемо; сигнатура `int` маскирует уязвимость при рефакторинге на `String`.
- **Consequence silence:** утечка креденшелов → компрометация БД; SQLi → чтение/изменение/удаление; утечки соединений → отказ сервиса. Утечка креденшелов и данных **необратима**.

---

## [INTERSECTION_RISKS]

1. **concurrency × resource_management:** shared Connection × отсутствие try-with-resources → недетерминированные, невоспроизводимые ошибки.
2. **security × observability:** SQLi × отсутствие audit log → инъекция может быть выполнена и не замечена.
3. **secrets × dev_process:** хардкод-креденшелы × отсутствие code review → секреты в VCS навсегда; ротация без перезаписи истории не помогает.
4. **scalability × reliability:** нет пула × утечки → каскадный отказ: сначала медленно, потом полностью недоступно.

---

## [ASSEMBLY]

**Иерархия:**
- **Core:** DbConnection (единая точка доступа, 4 метода, shared-состояние); PostgreSQL (localhost/db, роль `user`).
- **Service:** Caller-сервисы; источник данных для `id`/`names`/`sql`.
- **Infra:** JDBC driver; сеть JVM→PostgreSQL; VCS (носитель секретов). **Отсутствуют:** пул, таймауты, метрики, логи, health-checks.

**Связи:** Caller → getUser/bulkInsert/init/queryUnsafe → DriverManager/shared → PostgreSQL. Два пути к БД (per-call и shared) — источник противоречия.

**Critical path:** Caller → getUser/queryUnsafe → shared/DriverManager → PostgreSQL → (утечка/инъекция/исчерпание). Циклов нет.

---

## [REFACTORING]

**Вариант A — минимальный security-патч (hotfix, in-place):**
- `getUser` → PreparedStatement; try-with-resources; `setQueryTimeout(10)`.
- `bulkInsert` → try-with-resources; batch; транзакция.
- `queryUnsafe` → **удалить** (breaking).
- Креденшелы → env; ротация `pass` немедленно.
- **+** быстро, минимальный blast radius, закрывает 5 критичных. **−** нет пула, нет метрик.

**Вариант B — DAO + HikariCP (рекомендуемый, целевой):**
- Интерфейс `UserDao` + `JdbcUserDao` на HikariCP; `DbConnection` удаляется.
- Креденшелы из env; `queryUnsafe` не переносится; `bulkInsert` → batch.
- **+** пул, таймауты, backpressure, тестируемость. **−** breaking для вызывающих, деплой-изменения.

**Вариант C — полный рефакторинг (транзакции/retry/circuit breaker/audit/SLO):** избыточен для 40 строк; оправдан только если сервис под прод-нагрузкой (данных нет).

**Решение:** A как немедленный hotfix, B как целевой. Ротация пароля — **до** деплоя.

---

## [PARALLELS]

- **Паттерн:** «static utility + stateful singleton» — классический анти-паттерн; в JDBC-мире эквивалент — «connection per call без пула» (anti-pattern из JDBC best practices).
- **Аналогия:** `queryUnsafe` ≈ `Runtime.exec(userInput)` — публичный метод, принимающий произвольную команду.
- **Сравнение с нормой:** стандарт — DAO + пул (HikariCP) + PreparedStatement + try-with-resources + env-секреты. Здесь нарушены все пять.

---

## [TESTS]

**Покрытие:** 0%. **Нужно:**
- unit: `getUser` с параметризованным `id` (в т.ч. попытка инъекции `1 OR 1=1`).
- unit: `bulkInsert` с исключением в середине — соединение закрыто.
- concurrency: параллельные `queryUnsafe` (должен упасть/быть удалён).
- integration: пул под нагрузкой, метрика active/idle, отсутствие утечек.
- security: fuzz `id`/`sql`.
- smoke: старт с креденшелами из env.

**Edge cases:** `id` не существует → null; `names` пустой; SQLException в середине bulkInsert; `init()` дважды; `queryUnsafe("DROP TABLE users")`.

---

## [ACTION]

- **NOW:** ротировать пароль `pass`; инвентаризировать, кто ещё использует эти креденшелы; удалить `queryUnsafe` из публичного API (или закрыть доступ).
- **TODAY:** вариант A — PreparedStatement в `getUser`, try-with-resources в `getUser`/`bulkInsert`, `setQueryTimeout(10)`, креденшелы → env.
- **TOMORROW:** вариант B — `UserDao` + `JdbcUserDao` на HikariCP; batch в `bulkInsert`; удалить `DbConnection`.
- **LATER:** метрики пула, audit log, SLO, health-checks, тесты.

---

## [QUESTIONS]

1. Есть ли данные о RPS, размере БД, размере `names[]`? Без них `pool_size` не тюнится.
2. Кто ещё использует креденшелы `"user"/"pass"`? Ротация может сломать другие сервисы.
3. Есть ли индекс на `users(id)`? Влияет на план запроса после PreparedStatement.
4. `queryUnsafe` вызывается из внешнего слоя или только из доверенного кода?
5. Переписана ли история VCS? Ротация без перезаписи не устраняет утечку.

---

## [FUNC:FULL]

- **ECON:** effort A ~4–6h, B ~2–3 дня; cost $0 (библиотека HikariCP бесплатна); ROI высокий (устранение необратимых уязвимостей); budget — не задан; cloud delta $0 (инфра не меняется); cost of delay — необратимая утечка креденшелов и данных при каждом дне промедления.
- **FAIL:** критично — SQLi в `getUser`, произвольный SQL в `queryUnsafe`, хардкод-креденшелы, утечки соединений, гонка на shared; cascade — исчерпание соединений → отказ БД → отказ downstream; recovery — ротация пароля + аудит доступа + деплой фикса; откат кода не отменяет утечку.
- **METRICS:** codebase ~40 строк, 4 метода, 1 поле, 1 константа; deps 2 (java.sql, java.util.concurrent — второй dead); tests 0%; perf — DriverManager per call, bulkInsert без batch; quality — resilience_score 1/10; infra — нет пула/таймаутов/метрик/логов.
- **ALTERNATIVES:** языки — n/a (Java-контекст); фреймворки — HikariCP (пул), Spring JDBC/JPA (опционально); БД — PostgreSQL (не меняется); инфра — env/vault для секретов; паттерны — DAO, DI, try-with-resources, PreparedStatement, batch.
- **EVOLVE:** coupling 2/10 (прямой JDBC, нет абстракции); abstractions 1/10 (нет интерфейса); growth 2/10 (любое изменение затрагивает всех); friction высокий (две стратегии соединений, shared-состояние); вариант B поднимает overall до ~7.
- **COMPARE:** A — time ~4–6h, cost $0, risk низкий (hotfix), complexity низкая; B — time ~2–3 дня, cost $0, risk средний (breaking), complexity средняя; C — time ~1–2 недели, cost $0 + SRE-время, risk низкий, complexity высокая (over-engineering для 40 строк).

---

## [MANDATORY BASE]

1. **ECONOMICS:** time A ~4–6h, cost $0, при условии что ротация пароля выполняется параллельно и не блокирует деплой.
2. **RISKS:** критично — SQLi, произвольный SQL, хардкод-креденшелы, утечки, гонка; важно — нет пула/таймаутов/метрик/тестов, при условии что сервис в проде под нагрузкой.
3. **INFRASTRUCTURE:** pool_size=N (не задан в материале; для B — HikariCP default 10, тюнинг по RPS), при условии замера RPS и размера БД.
4. **CODE:** change ~40 строк → ~120 строк (A) или ~150 строк в 3 файлах (B), при условии сохранения сигнатур `getUser`/`bulkInsert`.
5. **ACTION:** now — ротация пароля + инвентаризация; tomorrow — вариант A; later — вариант B.
6. **TIMELINE:** NOW — ротация `pass`, удаление `queryUnsafe`; TODAY — PreparedStatement + try-with-resources + timeout; TOMORROW — DAO + HikariCP; LATER — метрики, audit, SLO, тесты.
7. **PRODUCTION IMPACT:** users N (не задано), deploy window — вне пика, rollback ~5 мин (код), но утечка креденшелов не откатывается.
8. **SLO IMPACT:** current N% (SLO не определены), after N% (не измеримо без метрик), при условии введения метрик пула и латентности.
9. **CLOUD COST:** current $N (unknown), projected $N (unknown), delta ±$0 — инфра не меняется, HikariCP — библиотека.
10. **ON-CALL:** new alerts — active_connections/pool_max > 0.8, acquire_timeout > 0, SQLException rate > 1%, leaked_connections > 0; runbook — отсутствует, требуется создать; escalation — level 2 (return_to_stage2 + force_emergency).

---

## [REFLEXION]

1. **Слабое место:** числа `pool_size`, RPS, размер БД отсутствуют в материале → **исправлено:** все параметры помечены как «требующие замера», не выдуманы; `cloud_cost` delta = 0 с обоснованием.
2. **Слабое место:** `risk_nodes[3]` (Сдвиг тезиса) был помечен «опционально», но маскирует SQLi и секреты → **исправлено:** повышен до «важно» (зафиксировано в stage2.cove.flagged).
3. **Слабое место:** конфликт «вариант A vs требование таймаутов» → **исправлено:** `statementTimeout` включён в вариант A как минимальная правка, не отложен до B.

**Итог:** accepted.

---

*Audit trail добавляется pipeline'ом (orchestrator.py) после Stage 5.*

[AUDIT_TRAIL]
audit_id: audit-2026-10-10-cdedc7
material_hash: sha256:e261f6aa379b002ea291da4c80d594723085de90cda65014195a3a7c7c0ecc2a
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

    vishap analyze data/real_cases/own/DbConnection.java
