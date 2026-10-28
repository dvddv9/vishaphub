# Case Study: SARD 501270-v1.0.1 — Metadata-Only (No Code) Refusal

**Material type:** metadata (external reference, no source code)
**Level:** D2
**task_type:** `other`
**Cost:** $0.004067
**Verdict:** SAFE
**Compliance:** none
**Session:** sess-2026-10-12-041601
**audit_id:** audit-2026-10-12-d9380a
**material_hash:** sha256:b41eac4c67844a16ed9be95710b02db3f35ca1b5af48b6f9bdd41cad37e18082  (64 hex, real SHA-256)

**Key findings:**
- **Conveyor REFUSED to analyze:** "Подтверждённых уязвимостей нет" — no code received
- **RN-1 (critical):** no source code — analysis based on metadata only
- **RN-5 (critical):** `language='other'` vs CWE-126/190 (implies C/C++)
- **RN-4 (important):** thesis shift — "run Conveyor" without code
- **RN-6 (important):** strategic avoidance of "no data — no analysis"
- **RN-8 (important):** over-read/overflow — sources of UB, crashes, RCE
- **13 Plan B items:** fetch + hash pin + clang-tidy + cppcheck + ASan/UBSan + fuzz
- **8-axis MATRIX:** Security: WARN, Facts: WARN, Resilience: FAIL
- **PARALLELS:** length-prefix → under-allocation → over-read → RCE (classic parser CVE chain)
- **This is the desired behavior:** honest refusal instead of hallucinated analysis

---

## Vishap Output

# SARD 501270-v1.0.1 — Conveyor Report (D2)

[ECHO] Материал: мета-инструкция со ссылкой на внешний SARD test case 501270-v1.0.1 (CWE-126 Buffer Over-read + CWE-190 Integer Overflow). Исходный код в материале отсутствует. Прогон Conveyor выполнен по метаданным; анализ кода не производился.

[ROUTE] stage0 → stage1 → stage2 → stage4. Fetch URL: NOT_EXECUTED. analyze.py: NOT_RUN. stop_action: return_to_stage2.

[CONCLUSION] Подтверждённых уязвимостей нет. CWE-126 и CWE-190 присутствуют только как декларация в метаданных SARD; признаков их наличия в коде не найдено (VERIFY: код не получен, статический анализ не запускался). Отчёт — гипотезы по метаданным, не security assessment. Единственный защитимый путь — Option A (fetch + hash pin + static analysis + fuzz).

[RISK_NODES]
- RN-1 (критично): нет исходного кода — анализ построен на метаданных.
- RN-5 (критично): противоречие language='other' vs CWE-126/190 (подразумевают C/C++).
- RN-2 (важно): CWE-126/190 — классы, не подтверждённые дефекты; один может маскировать другой.
- RN-4 (важно): сдвиг тезиса — «прогони Conveyor» при отсутствии кода.
- RN-6 (важно): стратегическое избегание явного «нет данных — нет анализа».
- RN-8 (важно): over-read/overflow — источники UB, крашей, потенциального RCE.
- RN-3, RN-7, RN-9, RN-10, RN-11 (опционально): версии SARD, производительность, масштабируемость, конкурентность, breaking changes — неприменимо/нет данных.

[PLAN_B]
- RN-1: fetch SARD 501270-v1.0.1, зафиксировать SHA-256, прогнать analyze.py --mode security.
- RN-2: подтвердить/опровергнуть CWE-126 и CWE-190 через clang-tidy + cppcheck + ASan/UBSan.
- RN-3: сверить версии SARD (v1.0.1 vs другие), зафиксировать эталонную.
- RN-4: переформулировать задачу как «анализ кода SARD 501270» после получения артефакта.
- RN-5: разрешить language='other' → 'c'/'cpp' по факту содержимого.
- RN-6: пометить «нет данных — нет анализа» как блокер до fetch.
- RN-8: fuzz-тесты граничных длин (0, INT_MAX, INT_MAX+1, отрицательная длина).
- RN-10: проверить многопоточность артефакта; при наличии — пересмотреть приоритет.
- FP-1: запросить исходник у заказчика или fetch из SARD.
- FP-2: не выводить CWE как подтверждённые без анализа кода.
- FP-3: fetch URL с проверкой целостности (HTTPS + pinning).
- FP-4: уточнить язык у заказчика.
- FP-5: запустить analyze.py после получения файла.

[ASSEMBLY] Артефакты для верификации: fetch_and_verify.sh (bash, curl + sha256 pin), analyze_501270.py (python, clang-tidy wrapper). Валидация: `python -c "import ast; ast.parse(open('analyze_501270.py').read())"`. Gantt: fetch+pin (1d) → clang-tidy+ASan (1d) → fuzz (1d) → confirm/refute CWE (1d).

[REFACTORING] Pipeline модульный (evolvability overall 6/10), но отсутствует стадия fetch/verify. Добавить: (1) fetch-слой с hash pinning, (2) retry policy на samate.nist.gov, (3) health-check toolchain, (4) явный переход metadata-only → code-based report.

[PARALLELS] Комбинация CWE-126 + CWE-190 типична для парсеров/декодеров с length-prefix полями: overflow длины → under-allocation → over-read → info-leak/RCE. Классическая цепочка, известная по CVE в парсерах изображений/архивов/сетевых протоколов.

[TESTS] Тесты в материале отсутствуют. Edge cases (гипотезы для последующего анализа): length=0, length=INT_MAX, length=INT_MAX+1 (overflow), length > фактический размер буфера, отрицательная длина (signed/unsigned mismatch). После fetch — libFuzzer/AFL++ harness.

[ACTION]
- NOW: пометить отчёт как metadata-only, не выдавать CWE как подтверждённые.
- TODAY: fetch SARD 501270-v1.0.1, зафиксировать SHA-256, разрешить language.
- TOMORROW: clang-tidy + cppcheck + ASan/UBSan на артефакте; fuzz граничных длин.
- LATER: подтвердить/опровергнуть CWE-126/190; при подтверждении — эскалация до critical, фикс до деплоя.

[QUESTIONS]
- VERIFY: разрешён ли fetch samate.nist.gov из CI-среды (network policy)?
- VERIFY: какая версия SARD эталонная — v1.0.1 или другая?
- VERIFY: язык артефакта — C или C++?
- VERIFY: артефакт — библиотека парсинга или standalone test case?
- VERIFY: есть ли у заказчика исходник локально (Option C)?

[FUNC:FULL]
- ECON: effort 1–2 eng-days (Option A), cost $0 cloud delta, ROI качественный — предотвращает mis-prioritized fix на неподтверждённом CWE; cost_of_delay = 1 день неверифицированной экспозиции CWE-126/190 при условии, что артефакт задеплоен.
- FAIL: критично — отсутствие кода (FP-1) и неверифицированные метаданные (FP-2); cascade: artifact_missing → analyze.py → verdict → все CWE-claims; recovery: fetch + hash pin + static analysis.
- METRICS: codebase unknown (код не получен), deps 0 (манифест отсутствует), tests 0, perf N/A, quality N/A, infra N/A (статический артефакт, не сервис).
- ALTERNATIVES: A — fetch-and-verify (recommended, 1–2d); B — metadata-only report (0.25d, отвергнут как deliverable); C — request source from client (0.5d + wait, единственный compliant путь при запрете fetch).
- EVOLVE: coupling 6/10, abstractions 5/10, feature_add 7/10, module_replace 8/10, overall 6/10; слабость — отсутствие fetch/verify стадии.
- COMPARE: A — 1–2d, $0, low risk, ground truth; B — 0.25d, $0, high risk (false-positive fix), non-transferable; C — 0.5d + wait, $0, medium risk, explicit consent.

[MANDATORY BASE]
1. ECONOMICS: time 1–2 eng-days, cost $0 cloud delta, при условии, что fetch разрешён и toolchain доступен в CI.
2. RISKS: критично — нет кода (RN-1), противоречие language/CWE (RN-5); важно — неверифицированные метаданные (RN-2), сдвиг тезиса (RN-4); при условии, что артефакт не получен.
3. INFRASTRUCTURE: pool_size=N/A, при условии, что артефакт — статический SARD test case, не сервис.
4. CODE: change 0 строк (код не получен), при условии, что fetch не выполнен.
5. ACTION: now — пометить metadata-only; tomorrow — fetch + clang-tidy + ASan.
6. TIMELINE: NOW — маркировка отчёта; TODAY — fetch + hash pin; TOMORROW — static analysis + fuzz; LATER — confirm/refute CWE.
7. PRODUCTION IMPACT: users unknown, deploy window N/A, rollback N/A, при условии, что артефакт не задеплоен; при деплое парсера — CWE-126/190 критичны.
8. SLO IMPACT: current N/A, after N/A, при условии, что SLO не определены (slo.defined=false).
9. CLOUD COST: current $0, projected $0, delta ±$0, при условии, что статический анализ идёт на существующем CI runner.
10. ON-CALL: new alerts 0, runbook N/A, escalation level 2 (return_to_stage2), при условии, что артефакт не в проде.

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | WARN | CWE-126/190 задекларированы, не подтверждены; threat_model гипотетический. |
| Facts | WARN | Все выводы — гипотезы по метаданным; код не получен. |
| Logic | OK | Противоречия (RN-5, collision) зафиксированы корректно. |
| Applicability | WARN | Отчёт применим только как interim placeholder до fetch. |
| Effectiveness | WARN | Без кода эффективность анализа близка к нулю. |
| Resilience | FAIL | resilience_score=2; нет tool_output, тестов, зависимостей. |
| Human factor | WARN | Риск: потребитель примет гипотезы за подтверждённые findings. |
| Clarity | OK | Пробелы и VERIFY-флаги явно помечены. |

[REFLEXION]
1. Слабое место: отчёт мог бы выглядеть как security assessment → исправлено явной маркировкой «metadata-only, не assessment» в [CONCLUSION] и [MATRIX].
2. Слабое место: числа без источника (eng-days, cost) → исправлено условиями в [MANDATORY BASE] (при условии fetch разрешён / toolchain доступен).
3. Слабое место: возможное противоречие между ACTION (fetch) и stop_action=return_to_stage2 → исправлено трактовкой return_to_stage2 как prerequisite к Option A, а не альтернативой.
Итог: accepted

---

*Примечание: [AUDIT_TRAIL] не сгенерирован — добавляется pipeline'ом автоматически. session_id: sess-2026-10-12-XXXXXX (из context).*

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-d9380a
material_hash: sha256:b41eac4c67844a16ed9be95710b02db3f35ca1b5af48b6f9bdd41cad37e18082
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

    vishap analyze data/real_cases/hard/sard-501270-metadata.txt

---

## Почему не сам SARD 501270

**Вопрос:** почему проанализирована мета-инструкция, а не сам файл SARD 501270-v1.0.1?

**Ответ:**

1. **Conveyor не имеет network access** (by design — security). Ссылка `https://samate.nist.gov/SARD/test-cases/501270/versions/1.0.1` **не открывалась**.
2. Задача содержала **только метаданные** (Test Case ID, CWE, ссылка), **не исходный код**.
3. Conveyor **честно отказался** анализировать — `RN-1 (critical): no source code`.
4. Это — **правильное поведение**: не выдумывать анализ без материала.

**Для реального анализа SARD 501270 нужно:**

1. Fetch файл вручную (curl / browser)
2. Зафиксировать SHA-256 оригинала
3. Подать файл в pipeline: `vishap analyze sard-501270.c`

**Это не баг Vishap, а его security-модель.** Conveyor работает только с поданным материалом — не ходит по ссылкам, не парсит URLs.

**Сравнение с чат-режимом:** LLM в чате мог бы «сымитировать» анализ SARD 501270 (галлюцинация). Conveyor в pipeline — отказался, потому что кода нет. **Это и есть разница инструмент vs симуляция.**
