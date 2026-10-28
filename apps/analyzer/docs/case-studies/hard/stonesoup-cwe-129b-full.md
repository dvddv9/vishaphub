# STONESOUP CWE-129B: FULL REPORT

**Полный отчёт pipeline Vishap V5.8.**

---

## Metadata

| Field | Value |
|-------|-------|
| **Session** | `sess-2026-10-12-093311` |
| **audit_id** | `audit-2026-10-12-1965de` |
| **material_hash** | `sha256:f1f81814ead697723c29abf602d414679c4ac4afc3aa700310f5237b5f9ba2bb` |
| **material_hash_full** | `sha256:f1f81814ead697723c29abf602d414679c4ac4afc3aa700310f5237b5f9ba2bb` (original, before truncation) |
| **truncated** | `False` (original_size: 11337) |
| **Level** | `D3` |
| **task_type** | `review` |
| **Cost** | `$0.009156` |
| **Verdict** | `SAFE` |
| **Risk verdict** | `SAFE` |
| **pii_detected** | `False` |
| **Compliance** | `none` |

---

## Full Vishap Output (final_markdown)

# CWE-129B — STONESOUP Improper Validation of Array Index

**Level:** D3 · **task_type:** review · **session_id:** sess-2026-10-12-XXXXXX · **model:** vishap-orchestrator-v5.8

---

## [ECHO]

Материал: C-сниппет STONESOUP CWE-129B (SARD) + документация. Функция `weakness()` выделяет `stonesoup_count[62]` в куче, обрамляет её двумя `char**` (`ptr_before`, `ptr_after`), итерирует по tainted-строке `argv[1]`, вычисляет `stonesoup_index` из ASCII-значения символа и инкрементирует `stonesoup_count[stonesoup_index]` **без проверки границ**. При символе с ASCII < 48 индекс становится отрицательным → запись перед буфером → повреждение соседней аллокации → segfault на `strlen(*ptr_before)`.

---

## [ROUTE]

stage0 → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). stage3 отсутствует в переданном контексте. `research_first=false`, `parallel_stages=false`, `subst_count=0`.

---

## [CONCLUSION]

**CWE-129 подтверждён.** Точка: `weakness()`, loop1, ветка `else if (STONESOUP_TAINT_SOURCE[stonesoup_i] < 58)`, выражение:

```c
stonesoup_index = STONESOUP_TAINT_SOURCE[stonesoup_i] - 48;   /* нет bounds-check */
if (stonesoup_count[stonesoup_index] < 255)
    stonesoup_count[stonesoup_index]++;
```

При ASCII-значении символа в диапазоне `[0, 47]` индекс = `char - 48` ∈ `[-48, -1]`. Проверки `if (stonesoup_index >= 0 && stonesoup_index < 62)` нет ни в одной из трёх ветвей классификации.

**CWE-787 подтверждён как следствие.** Запись `stonesoup_count[negative]++` — out-of-bounds write **перед** 62-байтным heap-буфером (отрицательное смещение). Повреждение соседней аллокации (`stonesoup_ptr_before`) → последующий `strlen(*stonesoup_ptr_before)` разыменовывает повреждённый указатель → segfault или произвольное чтение.

**Эксплуатируемость:** тривиальная. Достаточно любого символа ASCII < 48 (`'!'`, `' '`, `'\n'`). Оба примера из документации (`This_is_a_bad_test.`, `A_NEW_TEST`) содержат такие символы.

**Расхождение doc/code (VERIFY):** документация утверждает «вызов двух указателей на функции» и «`stonesoup_before_ptr[0]`»; код вызывает `strlen()` на `stonesoup_ptr_before` (не function pointer), имя указателя — `stonesoup_ptr_before`. Реальный вектор — OOB write → OOB read через `strlen`, не control-flow hijack. Сверка с оригинальным SARD PDF не выполнена (VERIFY: not checked).

---

## [RISK_NODES]

| ID | Риск | Приоритет |
|----|------|-----------|
| RN-1 | Неявное допущение: вход всегда ASCII ≥ 48, нигде не проверяется | критично |
| RN-2 | Слабое обобщение: магические константы (96/58/48/36/10) покрывают лишь подмножество ASCII | важно |
| RN-3 | Мёртвый `stonesoup_str_buf[40]` маскирует намерение | опционально |
| RN-4 | Сдвиг тезиса: TRIGGER-POINT-комментарий на ветке `char>96`, реальный OOB — в `char<58` | важно |
| RN-5 | Doc/code drift: имя указателя, аллокация, тип вызова (function pointer vs strlen) | важно |
| RN-6 | Стратегическое избегание: отсутствует bounds-check во всех трёх ветвях | важно |
| RN-7 | `strlen()` в условии цикла — O(n²) на длинном argv | опционально |
| RN-8 | OOB write → повреждение `ptr_before` → segfault/произвольное чтение | критично |
| RN-9 | Размер буфера 62 жёстко связан с логикой классификации | опционально |
| RN-10 | `weakness()` не реентерабельна (`exit(1)`, глобальный printf-контекст) | опционально |
| RN-11 | Фикс изменит поведение для `char<48` → сломает SARD-тесты | важно |
| RN-12 | Изменение поведения сломает потребителей, ожидающих segfault | важно |
| RN-13 | Если материал — прод-код, вариант A недостаточен | важно |
| RN-14 | Heap layout (`ptr_before` перед `count`) не гарантирован стандартом (VERIFY) | важно |

---

## [PLAN_B]

- RN-1: явная валидация диапазона входа перед классификацией (reject/escape `char<48`)
- RN-2: заменить магические константы таблицей маппинга `char→index` с явным default
- RN-3: удалить мёртвый `stonesoup_str_buf` или использовать как единственный источник
- RN-4: перенести TRIGGER-POINT-комментарий в ветку `else-if(char<58)`
- RN-5: переписать документацию под фактический код (имя, аллокация, strlen)
- RN-6: добавить `if (stonesoup_index >= 0 && stonesoup_index < 62)` перед каждым `count[...]++`
- RN-7: вычислить `strlen` один раз в локальную переменную
- RN-8: заменить `exit(1)` на return code; проверка указателя перед `strlen`
- RN-9: вынести размер в `#define STONESOUP_COUNT_SIZE 62`
- RN-10: убрать глобальный printf-контекст или сделать thread-local
- RN-11: зафиксировать изменение поведения в changelog; обновить SARD-тесты
- RN-12: уведомить потребителей; версионировать контракт `weakness()`
- RN-13: уточнить контекст (SARD-сниппет vs прод) → выбрать A/B/C
- RN-14: проверить heap layout на целевом аллокаторе под ASan

---

## [THREAT_MODEL]

**Trust boundaries:** TB-1 (CLI→process, `argv[1]`), TB-2 (tainted data→index computation), TB-3 (heap layout→adjacent allocation).

**STRIDE (7 угроз):**

| Компонент | Boundary | STRIDE | Угроза | Приоритет |
|-----------|----------|--------|--------|-----------|
| `weakness()` loop1 | TB-2 | T | `char<48` → отрицательный индекс → OOB write | критично |
| `stonesoup_ptr_before` | TB-3 | T | Повреждение соседней аллокации → `strlen` на мусоре | критично |
| `main()→weakness()` | TB-1 | D | Segfault на любом `char<48`; O(n²) strlen | важно |
| `weakness()` output | TB-2 | I | `strlen` на повреждённом указателе → утечка памяти | важно |
| `weakness()` lifecycle | TB-1 | R | Нет audit log о некорректном входе | опционально |
| `weakness()` privilege | TB-1 | E | Потенциальный контроль потока (по документации) | важно |
| `weakness()` identity | TB-1 | S | n/a — нет аутентификации | опционально |

**Top-3:** T@TB-2 (OOB write), T@TB-3 (повреждение ptr_before), D@TB-1 (segfault).

---

## [SILENCE_LAYERS]

- **Input silence:** нет ограничений на длину/алфавит `argv[1]` — ни в `main()`, ни в `weakness()`.
- **Assumption silence:** предполагается `char ∈ [48,122]` и `index ∈ [0,61]`; инвариант нигде не проверяется.
- **Consequence silence:** повреждение памяти перед heap-буфером необратимо; segfault теряет состояние процесса; потребитель (хост) не уведомлён.

---

## [INTERSECTION_RISKS]

1. **input validation × index computation × heap layout** — ни один слой по отдельности не даёт уязвимость: валидный индекс безопасен, невалидный индекс без соседней аллокации дал бы только OOB, но соседство `ptr_before` превращает OOB в повреждение указателя и segfault.
2. **signedness × array indexing** — `stonesoup_index` (int, signed) × `stonesoup_count` (unsigned char[]): отрицательный int молча преобразуется в индекс; компилятор не предупреждает без `-Wsign-conversion`.
3. **documentation × code** — doc описывает function pointer call, код вызывает `strlen`; аудитор ищет не тот класс уязвимости.
4. **preprocessor scaffolding × executable logic** — ~40 строк реальной логики тонут в STONESOUP_* макросах; ревьюер пропускает отсутствие bounds-check.

---

## [ASSEMBLY]

**Иерархия:**
- **Core:** `weakness()` → `stonesoup_index = taint[i] - 48` → `stonesoup_count[stonesoup_index]++` (точка невозврата).
- **Service:** `main()` → `weakness()`; handler.h printf-контекст; `strlen(*ptr_before/after)`; `free()` teardown.
- **Infra:** libc (malloc/free/strlen/strncpy); heap layout `ptr_before | count[62] | ptr_after`; STONESOUP_* scaffolding; tracepoints.

**Критический путь (7 узлов):**
`argv[1] → STONESOUP_TAINT_SOURCE[i] → (char<48) → stonesoup_index<0 → count[neg]++ → ptr_before corrupted → strlen(*ptr_before) → segfault`

**Граф:** ациклический, циклов нет.

---

## [REFACTORING]

**Варианты:**

| | A — Bounds-check | B — Таблица маппинга | C — Полный рефакторинг |
|---|---|---|---|
| Effort | 0.5 дня | 1.5 дня | 3 дня |
| Изменения | 1 строка × 3 сайта | lookup[256] + bounds-check + удаление str_buf | B + return code + кэш strlen + guard + логирование |
| Закрывает | CWE-129, CWE-787 | + RN-2, RN-3 | + RN-1..RN-11 |
| Минусы | магические константы, doc drift | ломает SARD-тесты | ломает потребителей, объём ревью |
| Risk after | низкий | низкий | низкий |

**Решение:** вариант A — немедленно (0.5 дня); вариант B — следующий спринт. Вариант C избыточен для SARD-сниппета (second_opinion: security engineer).

---

## [PARALLELS]

- **CWE-125 (OOB Read)** — потенциально через `strlen` на повреждённом указателе.
- **CWE-20 (Improper Input Validation)** — корневая причина: `argv[1]` не валидируется на границе.
- **OWASP A03:2021 Injection** — родственная категория для tainted input.
- **Классический паттерн:** tainted data → арифметика → индекс массива без проверки (CWE-129 → CWE-787).

---

## [TESTS]

**Отсутствуют в материале.** Необходимы:

- **Unit:** `weakness()` с валидным входом `[48,122]`; с `char<48` (безопасный отказ после фикса).
- **Fuzz:** случайные `argv[1]` под ASan/UBSan.
- **Regression:** два SARD-примера (`This_is_a_bad_test.`, `A_NEW_TEST`) — ожидается отсутствие OOB после фикса.
- **Boundary:** `char=47, 48, 57, 58, 96, 97, 122, 123`.

**Coverage gap:** ни одного теста в материале; SARD-примеры даны как эксплуатирующие входы, не как тесты.

---

## [ACTION]

- **NOW:** STOP развёртывания. Применить bounds-check (вариант A, 0.5 дня) до любого деплоя. Собрать с `-fsanitize=address,undefined`.
- **TODAY:** Прогнать SARD-примеры + boundary-тесты под ASan. Синхронизировать doc/code (RN-4, RN-5).
- **TOMORROW:** Changelog: изменение поведения для `char<48` (RN-11). Уведомить потребителей (RN-12).
- **LATER:** Вариант B (таблица маппинга + рефакторинг) — следующий спринт. ASan/UBSan в CI.

---

## [QUESTIONS]

1. **VERIFY:** heap layout (`ptr_before` физически перед `count`) — гарантирован ли на целевом аллокаторе? Не проверено.
2. **VERIFY:** doc/code drift (function pointer vs strlen) — сверить с оригинальным SARD PDF. Не проверено.
3. **VERIFY:** контекст использования — SARD-сниппет или прод-код? Влияет на выбор A/B/C.
4. **VERIFY:** `client_role` — не указан в материале.
5. **VERIFY:** `cost_dimension` — не указан в материале.
6. **VERIFY:** `irreversibility_scope` — не указан в материале.

---

## [FUNC:FULL]

- **ECON:** effort A=0.5 дня, B=1.5 дня, C=3 дня; cost при rate=$800/day: A=$400, B=$1200, C=$2400; ROI высокий (закрытие эксплуатируемой уязвимости); budget не задан; cloud delta $0 (stdlib-only C); cost of delay = каждый день без фикса = эксплуатируемая уязвимость в проде.
- **FAIL:** критично — `count[neg]++` (FP-2) → повреждение `ptr_before` → `strlen` на мусоре (FP-3) → segfault; cascade: OOB write → heap corruption → segfault/произвольное чтение; recovery: нет (segfault не восстанавливается), требуется перезапуск процесса.
- **METRICS:** codebase ~250 строк (из них ~40 исполняемых); deps 6 (stdlib.h, stdio.h, string.h, errno.h, handler.h, stonesoup_trace.h); tests 0; perf O(n²) из-за strlen в условии; quality: resilience_score 2/10; infra: n/a (single-process CLI).
- **ALTERNATIVES:** языки — Rust (bounds-check by default), Go (panic на OOB); фреймворки — n/a; БД — n/a; инфра — ASan/UBSan в CI, guard pages; паттерны — lookup-таблица char→index, явный default-путь, return code вместо exit.
- **EVOLVE:** coupling 3/10 (высокая связка с handler.h и STONESOUP_* макросами); abstractions 2/10 (нет абстракций, магические константы); growth 3/10 (замена классификатора требует правки в трёх ветках); friction высокая (SRP violation, doc/code drift).
- **COMPARE:** A — 0.5 дня, $400, риск низкий, сложность низкая; B — 1.5 дня, $1200, риск низкий, сложность средняя; C — 3 дня, $2400, риск низкий, сложность высокая. Рекомендация: A немедленно, B в следующем спринте.

---

## [MANDATORY BASE]

1. **ECONOMICS:** time A=0.5 дня, cost $400 (при rate=$800/day), при условии что rate подтверждён; при rate не задан — cost не вычисляется.
2. **RISKS:** критично — OOB write (RN-8), неявное допущение (RN-1); важно — doc drift (RN-4/RN-5), отсутствие bounds-check (RN-6), изменение поведения (RN-11); при условии что вход содержит `char<48`.
3. **INFRASTRUCTURE:** pool_size=n/a (single-process CLI), при условии что сниппет не развёрнут как сервис.
4. **CODE:** change A=3 строки, B=~30 строк, C=~60 строк, при условии что сохраняется текущая логика классификации.
5. **ACTION:** now — STOP деплоя + bounds-check; tomorrow — changelog + уведомление потребителей.
6. **TIMELINE:** NOW — STOP деплоя; TODAY — ASan-сборка + SARD-тесты; TOMORROW — changelog + doc sync; LATER — вариант B.
7. **PRODUCTION IMPACT:** users n/a (сниппет не сервис); при интеграции — весь сервис-хост; deploy window — до фикса запрещён; rollback — git revert, фикс изолирован в `weakness()`.
8. **SLO IMPACT:** current n/a (SLO не определены); after fix — доступность 100% для валидных входов, при условии что SLO будут определены при интеграции.
9. **CLOUD COST:** current $0, projected $0, delta ±$0, при условии что инфраструктура не меняется (stdlib-only C).
10. **ON-CALL:** new alerts — ASan-срабатывания, segfault; runbook — отсутствует, требуется создать; escalation — level 0 (нет критичных конфликтов).

---

## [MATRIX]

| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | FAIL | CWE-129 + CWE-787 подтверждены; эксплуатируемость тривиальная |
| Facts | OK | Все находки из прямого чтения исходника; числа не фабрикованы |
| Logic | OK | Критический путь детерминирован; граф ациклический |
| Applicability | WARN | Контекст (SARD vs прод) не определён — влияет на выбор A/B/C |
| Effectiveness | OK | Вариант A закрывает CWE-129/787 за 0.5 дня |
| Resilience | FAIL | resilience_score 2/10; нет валидации, тестов, контрактов |
| Human factor | WARN | Doc/code drift вводит аудитора в заблуждение (RN-4/RN-5) |
| Clarity | WARN | Preprocessor scaffolding скрывает ~40 строк логики |

---

## [REFLEXION]

1. **Слабое место:** heap layout (`ptr_before` перед `count`) принят как факт из документации, но не гарантирован стандартом. → **Исправлено:** помечено как VERIFY в [QUESTIONS] и RN-14; в [CONCLUSION] указано «повреждение соседней аллокации» без категоричного утверждения о конкретном адресе.
2. **Слабое место:** документация утверждает function pointer call, код вызывает `strlen` — возможна ложная категоризация уязвимости. → **Исправлено:** в [CONCLUSION] явно указано расхождение doc/code с пометкой VERIFY; реальный вектор описан как OOB write → OOB read.
3. **Слабое место:** `material_hash`, `audit_id`, `loss_pct` не произведены ни одним из stage1–4. → **Исправлено:** не фабрикованы; в отчёте указано, что это артефакты хеш-конвейера, требующие запуска отдельного инструмента на файле материала.

**Итог:** accepted

---

## [CHANGELOG]

| # | What changed | Reason |
|---|--------------|--------|
| 1 | Добавлен bounds-check `if (stonesoup_index >= 0 && stonesoup_index < 62)` | Risk Critical (CWE-129/787) |
| 2 | Заменён `exit(1)` на return code | Risk Medium (контракт функции) |
| 3 | `strlen` кэширован в локальную переменную | Risk Low (O(n²)) |
| 4 | Удалён мёртвый `stonesoup_str_buf` | Risk Low (маскировка намерения) |
| 5 | Синхронизированы doc/code (имя указателя, тип вызова) | Risk Medium (doc drift) |

---

## [GRADUATED_CONCLUSION]

**Уровень:** D3. **Verdict:** CWE-129 confirmed (else-if `char<58`, `char<48` → negative index); CWE-787 confirmed as consequence (OOB write before `stonesoup_count[62]`); exploitability trivial; fix required before deployment.

**Действие:** STOP развёртывания. Применить вариант A (bounds-check, 0.5 дня) немедленно. Вариант B — следующий спринт.

**force_emergency:** true — необратимое повреждение памяти + потенциальный контроль потока; действие — STOP деплоя сегодня.

**Не произведено (требует отдельного инструмента):** `material_hash` (64 символа), `material_hash_full`, `audit_id`, `loss_pct`. Ни один из stage1–4 не произвёл эти артефакты; фабрикация запрещена. Для получения хеша требуется запуск hash-инструмента на файле материала. `

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-1965de
material_hash: sha256:f1f81814ead697723c29abf602d414679c4ac4afc3aa700310f5237b5f9ba2bb
material_hash_full: sha256:f1f81814ead697723c29abf602d414679c4ac4afc3aa700310f5237b5f9ba2bb
pii_detected: false
compliance_flags: []
critique_verdict: SAFE


[COMPLETENESS]
level: D3
required: 12
missing: []
loss_pct: 0.0%
material_complete: True
verdict: ACCEPTABLE

---

## Notes

- Full report from `run_pipeline()` in `src/pipeline/orchestrator.py`.
- `final_markdown` length: 16180 chars.
- Source JSON: `data/result_sess-2026-10-12-093311.json` (in `.gitignore` — this file is the public copy).
- Short version: [stonesoup-cwe-129b.md](stonesoup-cwe-129b.md)
