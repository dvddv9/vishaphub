# Case Study: PostgreSQL execMain.c — Snapshot Leak, Privilege Escalation via Hook

**Source:** `src/backend/executor/execMain.c`
**Language:** C
**Level:** D4
**Cost:** $0.00877
**Truncated:** Yes (101346 -> 12000 chars)
**Session:** sess-2026-10-10-145038
**Verdict:** SAFE

---

## Vishap Output

# PostgreSQL `execMain.c` — D4 Analysis

**Session:** sess-2026-10-12-XXXXXX · **Model:** vishap-orchestrator-v5.8 · **Level:** D4 · **Material:** C source, PostgreSQL executor core (slice truncated mid-`standard_ExecutorRun`)

---

## [ECHO]

Материал — `src/backend/executor/execMain.c`, ядро исполнения запросов PostgreSQL. Виден срез: `ExecutorStart` / `standard_ExecutorStart` (полностью) и `ExecutorRun` / `standard_ExecutorRun` (обрывается на `because various par...`). `ExecutorFinish` и `ExecutorEnd` объявлены в шапке, но в срезе отсутствуют. 28 внутренних заголовков, hook-механизм для плагинов, 9 статических forward-деклараций. `subst_count=0`, emergency-маркеров в материале нет. Stage0 выставил 4 VERIFY-флага (output_goal, client_role, cost, irreversibility — все unknown). Stage4 вернул `force_emergency: true` и `return_to_stage2: true` (2 критических конфликта).

---

## [ROUTE]

stage0 → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → **stage5 (transmitter)**. `research_first=false`, `parallel_stages=false`. Stage4 эскалировал обратно в stage2 — но в данном прогоне pipeline доставил результат как есть, с флагом `force_emergency`. Трансмиттер собирает финальный Markdown из имеющихся stage1–4 без повторного прогона.

---

## [CONCLUSION]

`execMain.c` — зрелый, плотно документированный код ядра PostgreSQL с чистой четырёхфазной абстракцией (Start/Run/Finish/End) и hook-механизмом для расширений. **Критические риски не в самом коде, а в контрактах, которые он предполагает, но не проверяет в production-сборке:**

1. **FP-1 (критично):** `InitPlan()` — точка невозврата. Если caller (`pquery.c`) не оборачивает `ExecutorStart` в `PG_TRY/PG_CATCH`, ERROR в `InitPlan` утекает `EState` + 2 snapshot'а. Утечка snapshot → рост xmin horizon → блокировка VACUUM → раздувание таблиц → disk full. **Необратимо без restart backend'а или PITR.**
2. **FP-3 / SEC-1 (критично):** `ExecutorCheckPerms_hook` позволяет плагину вернуть `true` для любой проверки прав — privilege escalation до суперпользователя, обход RLS/ACL. Ядро не арбитрирует конфликты hook'ов.
3. **FP-2 (критично):** `RegisterSnapshot` × 2 в `standard_ExecutorStart`; парный `UnregisterSnapshot` в `ExecutorEnd` **не виден в срезе** — верификация невозможна без полного файла.

**Вердикт:** код корректен для доверенного caller'а и доверенных плагинов. В production-сборке (NDEBUG) все контрактные инварианты защищены только `Assert`, который компилируется out. Это не дефект кода — это **архитектурное решение с известной ценой**, задокументированное в комментариях, но не подкреплённое runtime-защитой.

---

## [RISK_NODES]

| # | Узел | Приоритет | Суть |
|---|------|-----------|------|
| 1 | Неявное допущение (snapshot active) | важно | `Assert(GetActiveSnapshot() == queryDesc->snapshot)` — в release не проверяется; нарушение → тихая порча данных |
| 2 | Слабое обобщение (switch CmdType) | опционально | Закрытый enum; добавление CmdType требует правки ядра |
| 3 | Конкурирующая реализация (hooks) | важно | Два плагина, оба вызывающие `standard_*`, конфликтуют за порядок; ядро не арбитрирует |
| 4 | Сдвиг тезиса (EXPLAIN + Finish) | опционально | Комментарий обещает Finish после Run, но при `EXEC_FLAG_EXPLAIN_ONLY` `AfterTriggerBeginQuery` пропускается — контракт неявно ослаблен |
| 5 | Внутреннее противоречие (Assert estate==NULL) | важно | Повторный `ExecutorStart` в release → утечка EState + snapshot без диагностики |
| 6 | Стратегическое избегание (parallel writes) | важно | Запрет параллельных UPDATE/DELETE задокументирован только в комментарии; нет runtime-инварианта против обхода через FDW |
| 7 | Производительность (RegisterSnapshot) | опционально | Стоимость на каждый ExecutorStart; осознанный дизайн-выбор |
| 8 | **Надёжность (InitPlan ERROR)** | **критично** | Точка невозврата; ERROR без PG_TRY в caller → утечка EState + snapshot |
| 9 | Масштабируемость (palloc0_array) | опционально | Линейно по nParamExec; заметно для bulk prepared statements |
| 10 | Конкурентность (IsInParallelMode) | важно | Однократная проверка на входе — TOCTOU, если режим включается позже |
| 11 | Ломающие изменения (hook ABI) | важно | Изменение сигнатуры ломает pg_stat_statements, auto_explain, Citus, pg_hint_plan, pgaudit |

---

## [THREAT_MODEL]

**Компоненты:** `ExecutorStart/Run/Finish/End`, hook-переменные (5 шт.), `QueryDesc`/`EState`/`PlannedStmt`, `DestReceiver`, snapshot manager, AfterTrigger context, pgstat.

**Trust boundaries:**
- **TB-1** Caller (pquery.c/tcop) → Executor — доверие к контракту
- **TB-2** Extension/Plugin → Executor hooks — граница ядро/расширение
- **TB-3** Executor → DestReceiver — граница backend/внешний потребитель
- **TB-4** Executor → Snapshot manager — граница с MVCC

**STRIDE-угрозы (7, из них 2 критических):**

| Компонент | Boundary | STRIDE | Угроза | Приоритет |
|-----------|----------|--------|--------|-----------|
| `ExecutorCheckPerms_hook` | TB-2 | E | Плагин возвращает `true` для любой проверки прав → privilege escalation | **критично** |
| `standard_ExecutorStart` (InitPlan) | TB-1 | D | ERROR в InitPlan без PG_TRY → утечка EState + snapshot → DoS | **критично** |
| `standard_ExecutorStart` (snapshot reg) | TB-4 | R | RegisterSnapshot без UnregisterSnapshot → утечка snapshot, блокировка VACUUM | важно |
| `standard_ExecutorStart` | TB-1 | T | Подмена PlannedStmt caller'ом → исполнение произвольного плана | важно |
| `standard_ExecutorRun` (rStartup) | TB-3 | I | DestReceiver получает кортежи до RLS-фильтрации | важно |
| `standard_ExecutorStart` (switch) | TB-1 | T | Некорректный CmdType → `es_output_cid` не инициализирован | опционально |
| `pgstat_report_query_id` | TB-1 | I | query_id утечка в pg_stat_statements | опционально |

**Top-3:** TB-2/E (hook privilege escalation), TB-1/D (InitPlan leak), TB-4/R (snapshot leak).

**Не рассмотрено (flagged в stage2.cove):** TB-5 executor→FDW (внешний код), TB-6 executor→JIT (компиляция выражений).

---

## [SILENCE_LAYERS]

**Input silence:** нет цифр нагрузки — QPS, число backend'ов, типичный размер плана, частота ExecutorStart. Все оценки производительности — качественные.

**Assumption silence:** предполагается, что caller корректно обрабатывает error-path (PG_TRY/PG_CATCH, активный snapshot, однократный ExecutorStart). Контракт задокументирован, но не проверяется runtime.

**Consequence silence:** утечка snapshot → рост xmin horizon → блокировка VACUUM → раздувание таблиц → деградация → OOM/disk full. **Необратимо** без restart backend'а или `pg_resetwal`. Кто страдает: DBA, оператор БД, конечный пользователь.

---

## [INTERSECTION_RISKS]

1. **Hook-механизм × Read-only enforcement:** плагин через `ExecutorStart_hook` может вызвать `standard_ExecutorStart` с модифицированным `eflags`, обойдя `EXEC_FLAG_EXPLAIN_ONLY` или подменив `plannedstmt` до `ExecCheckXactReadOnly`. → Запись в read-only транзакции, порча данных на реплике.

2. **Assert-инварианты × Production build (NDEBUG):** все контрактные проверки исчезают в release. Ошибка caller'а → UB вместо диагностируемой ошибки. → Тихая порча памяти / двойная регистрация snapshot.

3. **IsInParallelMode × FDW/custom scan:** проверка однократна на входе. FDW, включающий параллелизм позже, обходит защиту. → Нарушение xmax-взаимоисключения `heap_update()` → lost update, порча данных.

4. **DestReceiver × RLS:** если RLS-фильтрация на уровне scan-узла, а DestReceiver получает кортежи до фильтрации (при ошибке планировщика) — утечка данных, защищённых RLS. → Нарушение изоляции арендаторов.

---

## [ASSEMBLY]

**Слои (снизу вверх):**
- **Infra:** MemoryContext (`es_query_cxt`), Snapshot manager, EState/QueryDesc/PlannedStmt, DestReceiver, tableam/heapam, FDW API, JIT subsystem
- **Service:** hook dispatch (5 переменных), `ExecCheckXactReadOnly`, `ExecCheckPermissionsModified`, AfterTrigger context, pgstat, InstrAlloc/InstrStart
- **Core:** `ExecutorStart/Run/Finish/End` + `standard_*`, `InitPlan`, `ExecutePlan`

**Критический путь:**
`ExecutorStart → standard_ExecutorStart → CreateExecutorState → RegisterSnapshot ×2 → InitPlan → (return) → ExecutorRun → ExecutePlan → ExecutorFinish → ExecutorEnd → UnregisterSnapshot ×2 → FreeExecutorState`

**Точка невозврата:** `InitPlan(queryDesc, eflags)` — после неё `ExecutorEnd` обязателен.

**Циклов в графе зависимостей нет.**

---

## [REFACTORING]

**Паттерны:** Hook/plugin dispatch (function-pointer + NULL-fallback), Facade над lifecycle, Template-method split (public wrapper + `standard_*`).

**Нарушения SOLID:**
- **SRP (частично):** `standard_ExecutorStart` смешивает memory-context management, read-only enforcement, operation dispatch, snapshot registration, instrumentation setup, trigger-context setup.
- **OCP (частично):** switch по `CmdType` требует правки ядра для нового типа.

**Code smells:** длинная функция `standard_ExecutorStart`; `Assert` как precondition (компилируется out); `elog(ERROR)` в default-ветке switch.

**Направления рефакторинга (из stage4.options):**
- **A** — Harden invariants in-place (`Assert` → `elog` под флагом `PG_HARDENED_CONTRACTS`). Не ломает ABI, минимальная цена. Минус: дивергенция от upstream.
- **B** — Runtime invariant layer + snapshot leak detector (GUC-gated). Детектирует FP-2 до повреждения xmin horizon. Минус: новый GUC, только детекция.
- **C** — Hook arbitration + plugin capability model. Адресует SEC-1. Минус: ломает ABI всех плагинов, требует core buy-in.
- **D** — Do nothing, document the risk (не оценён формально в stage4.cove — flagged).

---

## [PARALLELS]

- **MVCC snapshot lifecycle** ↔ **refcounted resource management** (RAII в C++): `RegisterSnapshot`/`UnregisterSnapshot` — ручной refcount без автоматического освобождения при ERROR.
- **Hook-механизм PostgreSQL** ↔ **middleware chain** в веб-фреймворках: цепочка перехватчиков без арбитража порядка.
- **Assert-based contracts** ↔ **design by contract** (Eiffel): контракты есть, но enforcement только в debug.
- **`standard_ExecutorStart`** ↔ **God function** в legacy-коде: много ответственностей, но каждая — часть единого lifecycle.

---

## [TESTS]

**В срезе тестов нет.** PostgreSQL использует regression tests (`src/test/regress`) и TAP tests (`src/test/modules`); `execMain.c` покрыт косвенно через SQL-тесты.

**Необходимые тесты (из stage2.tests):**
- **Unit:** `ExecutorStart` с NULL queryDesc (Assert), с неактивным snapshot (Assert)
- **Integration:** error-path в `InitPlan` → проверка `UnregisterSnapshot`
- **Concurrency:** параллельный UPDATE/DELETE → проверка запрета
- **Hook:** плагин, перехватывающий `ExecutorCheckPerms_hook` → проверка privilege escalation
- **RLS:** запрос с RLS-политикой → проверка фильтрации до DestReceiver

**Edge cases:** `EXEC_FLAG_EXPLAIN_ONLY` без Run/Finish; повторный `ExecutorStart` (release); `InitPlan` ERROR без PG_TRY; параллельный режим + INSERT; пустой `paramExecTypes` (NIL).

**Coverage:** не определимо из среза — требуется gcov/lcov на полной сборке.

---

## [ACTION]

**NOW (сегодня):**
1. **Верифицировать caller error-path:** проанализировать `pquery.c` и `tcop/postgres.c` на наличие `PG_TRY/PG_CATCH` вокруг `ExecutorStart`. Это корень FP-1 — без верификации все рекомендации могут быть в неверном слое.
2. **Получить полный `execMain.c`:** проверить `ExecutorEnd` на парный `UnregisterSnapshot` для `es_snapshot` и `es_crosscheck_snapshot` (FP-2).
3. **Аудит загруженных расширений:** какие плагины регистрируют `ExecutorCheckPerms_hook`? (SEC-1)

**TOMORROW:**
4. **Мониторинг:** включить `pg_stat_statements`, `log_min_duration_statement`, `track_io_timing`. Настроить алерт на `pg_stat_activity.backend_xmin` lag > 300s.
5. **Runbook:** документировать процедуру восстановления при утечке snapshot (restart backend через `pg_terminate_backend`, при кластерной утечке — restart кластера, при порче данных — PITR).

**LATER:**
6. **Оценить Option A/B/C** в зависимости от роли (upstream core vs managed fork vs extension developer).
7. **Расширить scope анализа** на `pquery.c`, `tcop/postgres.c`, `fdwapi.h`, JIT-подсистему (TB-5, TB-6).

---

## [QUESTIONS]

1. **Какова роль решающего?** Upstream PostgreSQL core developer, managed PostgreSQL provider (RDS/Aurora/Cloud SQL), extension developer, или DBA? От этого зависит выбор Option A/B/C/D.
2. **Какова цель анализа?** Code review, security audit, fork hardening, incident post-mortem, или обучение?
3. **Есть ли цифры нагрузки?** QPS, число backend'ов, типичный размер плана — без них все оценки производительности качественные.
4. **Верифицирован ли caller error-path?** Оборачивает ли `pquery.c` вызов `ExecutorStart` в `PG_TRY/PG_CATCH`?
5. **Какие расширения загружены?** Регистрируют ли они `ExecutorCheckPerms_hook`?
6. **Какая версия PostgreSQL?** CVE-риски определяются версией, а не `execMain.c`.

---

## [FUNC:FULL]

**ECON:** effort для верификации caller error-path ~4–8h (анализ `pquery.c` + `tcop/postgres.c` + regression tests); cost $0 (внутренний анализ); ROI высокий — предотвращает необратимую утечку snapshot; budget не определён (нет данных о команде); cloud delta $0 (in-process код, нет инфраструктурных изменений); cost of delay — при утечке snapshot: блокировка VACUUM → раздувание таблиц → disk full → cluster outage, восстановление через PITR (часы downtime + потеря данных с последнего backup'а).

**FAIL:** критические точки — FP-1 (`InitPlan` ERROR без PG_TRY → утечка EState + 2 snapshot'а), FP-2 (`RegisterSnapshot` без `UnregisterSnapshot` → рост xmin horizon), FP-3 (`ExecutorCheckPerms_hook` → privilege escalation); cascade — утечка snapshot → xmin horizon → VACUUM blocked → table bloat → disk exhaustion → cluster outage; recovery — `pg_terminate_backend` для одного backend'а, restart кластера при кластерной утечке, PITR при порче данных.

**METRICS:** codebase — `execMain.c` ~2000–3000 строк (полный файл, срез обрезан на ~5000 токенов); deps — 28 внутренних заголовков, внешних нет; tests — в срезе отсутствуют, покрытие косвенное через regression/TAP; perf — overhead `RegisterSnapshot` × 2 + `InstrAlloc` на каждый `ExecutorStart`, доля от общего времени запроса не определима без бенчмарков; quality — плотные комментарии (~1:1 к коду), pgindent-совместимый стиль, 30-летняя история; infra — per-backend, не пулится, `max_connections` управляет числом backend'ов.

**ALTERNATIVES:** языки — C обязателен (ядро PostgreSQL); фреймворки — N/A; БД — N/A (это и есть СУБД); инфра — N/A (in-process); паттерны — Option A (harden contracts in-place), Option B (runtime invariant layer + snapshot leak detector), Option C (hook arbitration + capability model), Option D (do nothing, document — не оценён формально).

**EVOLVE:** coupling — высокий (28 заголовков, прямая зависимость от executor/catalog/access/rewrite/tcop/utils); abstractions — умеренные (QueryDesc/EState/DestReceiver — чистые швы, но lifecycle монолитен); growth — низкий (switch по CmdType закрыт, добавление команды требует правки ядра); friction — hook ABI публичный, но хрупкий; overall evolvability 4/10 (зрелый, но жёсткий; расширяемость только через hooks, ценой доверия).

**COMPARE:** time — верификация caller error-path 4–8h, полный аудит с FDW/JIT 2–3 дня; cost — $0 для внутреннего анализа, стоимость Option C (hook arbitration) — пересборка и ре-сертификация всех плагинов; risk — Option A низкий (не ломает ABI), Option B низкий (GUC-gated), Option C высокий (ломает ABI), Option D нулевой (но оставляет риск); complexity — Option A низкая, Option B средняя, Option C высокая, Option D нулевая.

---

## [MANDATORY BASE]

1. **ECONOMICS:** time 4–8h на верификацию caller error-path, cost $0, при условии что анализ ведётся внутренней командой без внешних консультантов; при привлечении внешнего аудита — $5k–15k.

2. **RISKS:** критично — FP-1 (InitPlan ERROR без PG_TRY → утечка snapshot, необратимо), FP-3 (ExecutorCheckPerms_hook → privilege escalation); важно — FP-2 (RegisterSnapshot без UnregisterSnapshot), FP-4 (ExecCheckXactReadOnly обход), FP-5 (IsInParallelMode TOCTOU); при условии что caller не верифицирован и плагины не аудированы.

3. **INFRASTRUCTURE:** pool_size=N/A (executor per-backend, не пулится), при условии что `max_connections` управляет числом backend'ов; memory — `es_query_cxt` per query + `palloc0_array(ParamExecData, nParamExec)`, при условии что размер плана пропорционален сложности запроса.

4. **CODE:** change — Option A ~50 строк (замена Assert на elog под флагом), Option B ~100 строк (GUC + leak detector), Option C ~200 строк (hook arbitration API), при условии что изменения вносятся в форк, а не в upstream.

5. **ACTION:** now — верифицировать caller error-path в `pquery.c`/`tcop/postgres.c`, получить полный `execMain.c`, аудит плагинов; tomorrow — мониторинг (`pg_stat_statements`, алерт на `backend_xmin` lag), runbook для утечки snapshot.

6. **TIMELINE:** NOW — верификация caller + полный файл; TODAY — аудит плагинов + мониторинг; TOMORROW — runbook + оценка Option A/B/C; LATER — расширение scope на FDW/JIT, оценка Option D.

7. **PRODUCTION IMPACT:** users N (не определено — нет данных о нагрузке), deploy window — minor version (замена бинарника + restart), rollback N min (restart backend'а ~секунды, restart кластера ~минуты), при условии что изменения вносятся в minor-версию.

8. **SLO IMPACT:** current N% (SLO не определены в `execMain.c`), after N% (не определимо без baseline), при условии что SLO задаются на уровне кластера (availability, p99 latency, throughput), а не executor'а.

9. **CLOUD COST:** current $0, projected $0, delta ±$0, при условии что `execMain.c` — in-process backend код, инфраструктурных изменений нет.

10. **ON-CALL:** new alerts — алерт на `pg_stat_activity.backend_xmin` lag > 300s, алерт на InitPlan error rate > 1/sec; runbook — процедура восстановления при утечке snapshot (restart backend → restart кластера → PITR); escalation — DBA/SRE → core team при подтверждённой утечке.

---

## [COMPLEXITY]

**Цикломатическая сложность:** `standard_ExecutorStart` — высокая (switch + вложенные if в CMD_SELECT case, ~15–20 ветвей); `standard_ExecutorRun` — средняя (не виден полностью); `ExecutorStart`/`ExecutorRun` (public wrappers) — низкая (1 if).

**Когнитивная сложность:** высокая для `standard_ExecutorStart` — смешаны memory management, read-only enforcement, operation dispatch, snapshot registration, instrumentation, trigger setup.

**Глубина вложенности:** max 3 (function → if → switch → case → if).

---

## [STRUCTURE]

**Модуль:** `src/backend/executor/execMain.c` — top-level executor interface.

**Публичный API:** 4 функции (`ExecutorStart`, `ExecutorRun`, `ExecutorFinish`, `ExecutorEnd`) + 5 hook-переменных.

**Приватный API:** 9 статических forward-деклараций (`InitPlan`, `CheckValidRowMarkRel`, `ExecPostprocessPlan`, `ExecEndPlan`, `ExecutePlan`, `ExecCheckPermissionsModified`, `ExecCheckXactReadOnly`, `EvalPlanQualStart`, `ReportNotNullViolationError`).

**Слои:** public interface → hook dispatch → standard implementation → local static helpers.

---

## [TEXTURE]

**Плотность:** высокая — плотный C с обширными блочными комментариями; соотношение комментариев к коду ~1:1 в видимом срезе.

**Стиль:** PostgreSQL backend C — табы, `/* */`, pgindent-совместимо, статические forward-декларации с маркером `end of local decls`.

**Документация:** обширный header-комментарий с контрактом интерфейса, порядком вызовов, hook-механизмом; inline-комментарии объясняют неочевидные решения (запрет параллельных записей, EXPLAIN как read-only, SELECT skip-triggers оптимизация).

---

## [SHADOWS]

**Breaks:** материал обрезан на середине `standard_ExecutorRun` (`because various par...` — неполное слово); `ExecutorFinish` и `ExecutorEnd` отсутствуют в срезе.

**Comment-code mismatch:** header-комментарий обещает 4 интерфейсные функции, срез содержит только 2 (не mismatch, а неполнота среза); комментарий про `ExecutorEnd` при abort не верифицируем без error-path кода.

**Blind spots:** `InitPlan`, `ExecutePlan`, `ExecEndPlan`, `ExecPostprocessPlan` — реализации не видны; `ExecutorFinish`/`ExecutorEnd` — тела не видны; hook-реализации (внешние плагины); определения `EState`/`QueryDesc`; гарантии lifetime memory-context; модель конкурентности executor'а (parallel workers, shared state).

---

## [SECURITY]

**Summary:** `execMain.c` — ядро исполнения запросов. Прямых injection-векторов нет (план уже скомпилирован), но есть косвенные: hook-механизм даёт полный контроль над исполнением, RLS-проверки делегированы `ExecCheckPermissionsModified` (не в срезе), read-only enforcement зависит от корректности `PlannedStmt`.

**Findings:**
- **SEC-1 (важно):** Hook-механизм как privilege escalation surface — `ExecutorCheckPerms_hook` позволяет плагину обойти RLS/ACL. Mitigation: ограничить загрузку плагинов, аудит расширений.
- **SEC-2 (важно):** Read-only enforcement зависит от `PlannedStmt` — единственный барьер `ExecCheckXactReadOnly`. Mitigation: defense-in-depth через нижние проверки в `heap_insert/update`.
- **SEC-3 (важно):** Assert-based инварианты не защищают production — все контрактные проверки компилируются out. Mitigation: `elog(ERROR)` для критичных инвариантов под флагом.
- **SEC-4 (опционально):** Отсутствие audit trail на уровне executor. Mitigation: pgaudit или `log_statement=all`.

**Secrets:** hardcoded secrets не обнаружено. Risk: none.

---

## [TEST_ANALYSIS]

**В срезе тестов нет.** PostgreSQL использует regression tests (`src/test/regress`) и TAP tests (`src/test/modules`). `execMain.c` покрыт косвенно через SQL-тесты.

**Необходимые тесты:** unit (NULL queryDesc, неактивный snapshot), integration (error-path в InitPlan → UnregisterSnapshot), concurrency (параллельный UPDATE/DELETE), hook (privilege escalation через ExecutorCheckPerms_hook), RLS (фильтрация до DestReceiver).

**Coverage:** не определимо из среза — требуется gcov/lcov на полной сборке.

---

## [DEPENDENCIES]

**Total:** 28 внутренних заголовков PostgreSQL backend. Внешних зависимостей нет.

**Outdated:** не определимо из среза — это внутренние заголовки, не внешние пакеты.

**CVE:** не определимо из среза — требуется сканирование версии PostgreSQL (CVE-2024-XXXX и т.д.). CVE-риски определяются версией PostgreSQL, а не `execMain.c`.

---

## [FAILURE_POINTS]

| ID | Точка | Приоритет | Причина |
|----|-------|-----------|---------|
| FP-1 | `InitPlan(queryDesc, eflags)` | **критическая** | Точка невозврата; ERROR без PG_TRY в caller → утечка EState + snapshot |
| FP-2 | `RegisterSnapshot` × 2 | **критическая** | Утечка snapshot → рост xmin horizon → блокировка VACUUM → раздувание таблиц |
| FP-3 | `ExecutorCheckPerms_hook` | **критическая** | Плагин может вернуть `true` для любой проверки прав → privilege escalation |
| FP-4 | `ExecCheckXactReadOnly(plannedstmt)` | важная | Единственный барьер против записи в read-only транзакции |
| FP-5 | `IsInParallelMode()` проверка | важная | Однократная проверка на входе — TOCTOU |
| FP-6 | `AfterTriggerBeginQuery` (условный) | опциональная | Пропуск при `EXEC_FLAG_EXPLAIN_ONLY` — контракт Finish неявно ослаблен |
| FP-7 | `dest->rStartup(dest, operation, tupDesc)` | опциональная | DestReceiver может упасть; ошибка после rStartup требует rShutdown в error-path |

---

## [EVOLVABILITY]

**Feature add:** 4/10 — switch по `CmdType` закрыт; добавление команды требует правки ядра.

**Module replace:** 3/10 — 28 заголовков, тесная связность с executor/catalog/access.

**Coupling:** 3/10 (высокая связность) — hook ABI публичный, но хрупкий.

**Abstractions:** 6/10 — `QueryDesc`/`EState`/`DestReceiver` — чистые швы, но lifecycle монолитен.

**Overall:** 4/10 — зрелый, но жёсткий; расширяемость только через hooks, ценой доверия.

---

## [AUTHOR_SOLUTIONS]

**Option A — Harden invariants in-place:** замена `Assert` на `elog(ERROR)` под флагом `PG_HARDENED_CONTRACTS`. Не ломает ABI, минимальная цена (~2 branch checks per ExecutorStart). Минус: дивергенция от upstream.

**Option B — Runtime invariant layer + snapshot leak detector:** GUC-gated детектор утечек snapshot + runtime-проверка `IsInParallelMode` в `ExecutorRun`. Детектирует FP-2 до повреждения xmin horizon. Минус: новый GUC, только детекция.

**Option C — Hook arbitration + plugin capability model:** API регистрации hook'ов с порядком и capability declaration. Адресует SEC-1. Минус: ломает ABI всех плагинов, требует core buy-in.

**Option D — Do nothing, document the risk:** не оценён формально в stage4.cove — flagged как «отклонён слишком быстро». Для upstream PostgreSQL может быть корректным ответом.

---

## [REFACTORING_PLAN]

**Фаза 1 (верификация, 4–8h):** анализ `pquery.c` и `tcop/postgres.c` на PG_TRY/PG_CATCH; получение полного `execMain.c`; проверка `UnregisterSnapshot` в `ExecutorEnd`.

**Фаза 2 (мониторинг, 1 день):** включить `pg_stat_statements`, `log_min_duration_statement`, `track_io_timing`; настроить алерт на `backend_xmin` lag > 300s; runbook для утечки snapshot.

**Фаза 3 (hardening, 1–2 недели):** выбор Option A/B/C/D в зависимости от роли; реализация в форке (не upstream); regression + TAP tests для error-path.

**Фаза 4 (расширение scope, 2–3 дня):** анализ FDW (TB-5), JIT (TB-6), `ExecCheckPermissionsModified`, `InitPlan`, `ExecutePlan`.

---

## [ECONOMICS]

**Effort:** верификация caller error-path 4–8h; полный аудит с FDW/JIT 2–3 дня; реализация Option A ~1 день, Option B ~2 дня, Option C ~1–2 недели.

**Cost:** $0 для внутреннего анализа; $5k–15k при внешнем аудите; Option C — стоимость пересборки и ре-сертификации всех плагинов (pg_stat_statements, auto_explain, Citus, pg_hint_plan, pgaudit).

**ROI:** высокий для верификации caller error-path — предотвращает необратимую утечку snapshot.

**Budget:** не определён (нет данных о команде).

**Cloud delta:** $0 — in-process код, инфраструктурных изменений нет.

**Cost of delay:** при утечке snapshot — блокировка VACUUM → раздувание таблиц → disk full → cluster outage; восстановление через PITR (часы downtime + потеря данных с последнего backup'а).

---

## [FAILURE_SCENARIO]

**Сценарий 1 (FP-1):** caller не оборачивает `ExecutorStart` в PG_TRY → `InitPlan` бросает ERROR (OOM при аллокации

[AUDIT_TRAIL]
audit_id: audit-2026-10-10-24866e
material_hash: sha256:9c70c894c35dd8e475d2914999fbf07d23f34fcf358a842f537d6e94074c537b
pii_detected: false
compliance_flags: []
critique_verdict: SAFE


[COMPLETENESS]
level: D4
required: 30
missing: ['[CONFLICT_RESOLUTION]', '[FINAL_METRICS]', '[FINAL_CALCULATIONS]', '[COMPLETENESS_CHECK]', '[GRADUATED_CONCLUSION]']
loss_pct: 16.7%
verdict: ACCEPTABLE

---

## Reproduce

    vishap analyze data/real_cases/hard/postgres_execMain.c
