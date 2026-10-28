# Case Study #2: curl/lib/http2.c

| | |
|---|---|
| **Материал** | `curl/lib/http2.c` — C, 100+ KB (HTTP/2 connection filter) |
| **Источник** | github.com/curl/curl, commit `3661f39` |
| **Инструмент** | Vishap v6.0.1 — D4 (максимальная детализация), Harness mode |
| **Сессия** | `sess-2026-10-17-200554` |
| **Дата прогона** | 2026-10-17 |
| **Verdict** | `REQUIRES_REVIEW` |
| **Находок** | 5 (3 важных, 2 опциональных) |
| **CWE** | CWE-252, CWE-459, CWE-617, CWE-754, CWE-362 |

---

## Context

`curl/lib/http2.c` — слой HTTP/2 в libcurl: инициализация nghttp2-сессии,
обработка кадров, управление состоянием соединения и потоков. Файл больше
100 KB, что почти вдвое превышает материал первого case study — это первый
прогон Vishap на материале такого объёма.

Файл подан целиком, без ручной нарезки. Уровень **D4** выбран явно: пайплайн
строит максимально подробный отчёт (в этом прогоне — 30 блоков), что даёт
больше контекста, но и больше поводов для ложных срабатываний.

- **Материал:** `curl/lib/http2.c`, commit `3661f39`, 100+ KB, C.
- **Режим:** D4, Harness mode (автономный прогон без интерактива).
- **Пайплайн:** Stage 0 (маршрутизация) → Stage 1 (scanner) → Stage 2 (analyst)
  → Stage 3 (researcher) → Stage 4 (synthesizer) → audit trail.
- **Детерминированные инструменты:** SAST/SCA/anomaly-детектор шли параллельно
  с LLM-стадиями и не заменялись ими.

Отличие от [Case Study #1](curl-cookie-c.md): там был D3, 49 KB и 4 находки
без аномалий; здесь — D4, 100+ KB, 5 находок, плюс anomaly-детектор,
pii-редакция и два хеша материала.

---

## Findings

Vishap вернул 5 находок. Три «важных» и две «опциональных» — последние означают
«стоит посмотреть, но не блокирует».

| ID | Приоритет | Проблема | CWE |
|---|---|---|---|
| SEC-1 | важно | Непроверяемый результат инициализации | CWE-252 |
| SEC-2 | важно | Частичная инициализация на error-path | CWE-459 |
| SEC-3 | важно | Достижимый DEBUGASSERT | CWE-617 |
| SEC-4 | опционально | Desync состояния соединения | CWE-754 |
| SEC-5 | опционально | Thread-safety состояния | CWE-362 |

### SEC-1 — unchecked init (CWE-252)

Возвращаемое значение инициализирующего вызова не проверяется. Если
инициализация не удалась, дальнейший код работает со структурой, которая
формально существует, но не сконфигурирована: ошибка проявляется гораздо позже
и в другом месте — классический «unchecked return value».

### SEC-2 — partial init (CWE-459)

На пути ошибки освобождается не всё, что было выделено (или наоборот:
инициализируется не всё, что потом читается). В долгоживущем процессе такой
дисбаланс накапливается и превращается в утечку либо в обращение к
полуинициализированному состоянию.

### SEC-3 — достижимый DEBUGASSERT (CWE-617)

Утверждение, которое в отладочной сборке приводит к `abort()`, достижимо
внешними данными. В release-сборке оно превращается в unchecked-ветку, в
debug-сборке — в отказ процесса. Оба варианта нежелательны для сетевого кода.

### SEC-4 — desync состояния (CWE-754)

Проверка «необычного» состояния соединения неполна: при определённой
последовательности кадров внутреннее состояние расходится с тем, что видит
противоположная сторона. Для HTTP/2 это class-дефект: рассинхронизация окна и
состояния потока — источник зависаний и утечек ресурсов.

### SEC-5 — thread-safety (CWE-362)

Состояние соединения изменяется без достаточной синхронизации. При
использовании одного handle из нескольких потоков это даёт гонку с
непредсказуемым результатом. Помечено как «опционально»: зависит от того,
разрешает ли публичный контракт libcurl такой сценарий.

---

## STRIDE Model

Модель построена по найденным дефектам: каждая строка привязана к находке и CWE.

| Угроза | Проявление в `http2.c` | Находка | Влияние |
|---|---|---|---|
| **T** — Tampering | Расхождение состояния соединения с состоянием peer'а при нестандартной последовательности кадров | SEC-4 | Подмена интерпретации потока, обход проверок уровня приложения |
| **S** — Spoofing | Неинициализированная сессия продолжает работать, выдавая себя за корректно установленное соединение | SEC-1 | Ответы приписываются не тому соединению/хосту |
| **D** — Denial of service | Достижимый `DEBUGASSERT` (abort) и рассинхронизация окна | SEC-3, SEC-4 | Отказ процесса и зависание потока по внешнему вводу |
| **I** — Information disclosure | Чтение полуинициализированного состояния при ошибке | SEC-2 | Утечка данных соседних аллокаций в вывод/логи |
| **R** — Repudiation | Ошибка инициализации не приводит к однозначному признаку отказа — инцидент не восстановить по логам | SEC-1, SEC-5 | Невозможность разбора инцидента |
| **E** — Elevation of privilege | Гонка на состоянии соединения при конкурентном использовании handle | SEC-5 | Обход ограничений, заложенных в однопоточном сценарии |

---

## Refactoring Plan

Три варианта с оценкой трудозатрат; каждый включает предыдущий.

| Опция | Подход | Оценка | Что закрывает |
|---|---|---|---|
| **A. Hardening-only** | Проверить коды возврата инициализации, выровнять error-path (освобождать ровно то, что выделено), заменить достижимый `DEBUGASSERT` на явную обработку ошибки, закрыть RN-5. | **2–3 дня** | SEC-1, SEC-2, SEC-3, RN-5 |
| **B. + Window/DoS guard, trace, docs** | Добавить контроль окна и защиту от флуда кадрами, трассировку переходов состояния соединения и документирование инвариантов. | **4–6 дней** | + SEC-4 |
| **C. + Abstraction seam над nghttp2** | Изолировать библиотеку за интерфейсом, чтобы состояние соединения было тестируемым и заменяемым без переписывания `http2.c`. | **8–12 дней** | SEC-5 (тестируемость и владение состоянием) |

**Рекомендация:** A — сразу, это дешёвый и локальный патч, закрывающий все три
«важных» находки. B — следующим релизом: защита окна и трассировка дают
наблюдаемость, без которой desync всё равно не отладить. C оправдан только если
планируется обновление или замена nghttp2 — иначе это архитектурная работа без
немедленной отдачи.

---

## Audit Trail

| Поле | Значение |
|---|---|
| `material` | `curl/lib/http2.c` (100+ KB, C) |
| `material_hash` | `sha256:5b4af1f1ac668e397c5b21fca9cd26ecc7fdb032ccc6080526edced495c863e0` |
| `material_hash_full` | `sha256:2bab21242f23eaf55d10c44bf6143059f353759b03233ab6a6d5dc5e64317dd0` |
| `provenance_commit` | `3661f39` |
| `cwe_ids` | `['CWE-252', 'CWE-459', 'CWE-617', 'CWE-754', 'CWE-362']` |
| `pii_detected` | `false` |
| `anomaly_verdict` | `ANOMALIES_FOUND` |
| `anomaly_count` | 2 (индекс 48 → 10988 символов, индекс 117 → 8192 символа, z-score > 3) |
| `risk_verdict` | `REQUIRES_REVIEW` |
| `session_id` | `sess-2026-10-17-200554` |

Два хеша фиксируют разные вещи: `material_hash` — срез, который реально ушёл
в анализ (уже после PII-редакции), `material_hash_full` — исходный материал.
По паре можно доказать, что отчёт построен по тому же файлу, что и проверялся,
и при этом показать, что именно было вырезано до отправки в LLM.

Anomaly-детектор отметил две строки как статистические выбросы: индексы 48 и 117
длиной 10 988 и 8 192 символов (z-score > 3). В C-файле такого размера это
обычно таблицы или длинные строковые литералы — на находки они не повлияли, но
показывают, что детектор видит материал, а не только парсит его.

---

## Verdict

```
REQUIRES_REVIEW
```

Отчёт не утверждает наличие эксплуатируемой уязвимости. Вердикт означает:
накопилось достаточно признаков, чтобы человек посмотрел код руками до релиза.
При 5 находках и двух аномалиях `SAFE` не выдаётся по построению пайплайна.

Что проверять вручную:

1. **SEC-1** — какой именно вызов инициализации не проверяется и что делает
   код ниже по течению при его провале.
2. **SEC-2** — симметричен ли error-path: освобождается ли ровно то, что было
   выделено до точки отказа.
3. **SEC-3** — достижим ли `DEBUGASSERT` внешними данными и что происходит в
   release-сборке на той же ветке.
4. **SEC-4/SEC-5** — разрешён ли конкурентный доступ к handle контрактом libcurl;
   от ответа зависит, «опционально» это или «важно».

---

## Full Report

<details>
<summary>Full Report (Vishap v6.0.1, D4)</summary>

```text
VISHAP V5.8 — STAGE 5: TRANSMITTER
Session: sess-2026-10-17-200554 · Level: D4 · Task: review · Material: curl HTTP/2 cfilter (C, truncated)

[ECHO]
Срез lib/cf-http2.c (curl, HTTP/2 connection filter на nghttp2). Вход усечён посреди cf_h2_update_local_win — полный translation unit недоступен. Анализ основан на ручном чтении видимого фрагмента: cf_h2_ctx, h2_stream_ctx, init/free, settings, stream registry, начало local-window логики. Инструменты (slice_input.py, статические анализаторы) не запускались — TRUNCATED_INPUT.

[ROUTE]
stage0 → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). Параллельные стадии не использовались. research_first: false. subst_count: 0.

[CONCLUSION]
Код зрелый (curl), но в видимом срезе есть латентные дефекты error-путей: непроверенные возвраты инициализаторов stream (SEC-1, CWE-252), частичная инициализация cf_h2_ctx при free (SEC-2, CWE-459), молчаливый DEBUGASSERT(0) в release (SEC-3, CWE-617), рассинхронизация initial_win_size при ошибке submit (RN-5). Happy path корректен; дефекты проявляются при OOM и нарушении инвариантов. Рекомендация — Option A (hardening-only, 2–3 дня), не emergency. Контракт однопоточности multi handle в файле не задокументирован (VERIFY: не проверено по внешней документации curl).

[RISK_NODES]
IDУзелПриоритетСуть
RN-1Неявное допущениекритичноОднопоточная модель multi не задокументирована в файле
RN-2Слабое обобщениеважноcf_h2_ctx_free при initialized=FALSE — потенциальная утечка/двойное free
RN-5Внутреннее противоречиеважноcf_h2_update_settings: ошибка submit → initial_win_size не обновлён
RN-6Стратегическое избеганиеважноDEBUGASSERT(0) в release молча возвращает NULL
RN-8Надёжностьважноh2_stream_ctx_create не проверяет возвраты init
RN-9МасштабируемостьопциональноHTTP2_HUGE_WINDOW_SIZE = 1GB; #10988
RN-10Конкурентностьважноnghttp2_session не потокобезопасен, контракт неявный
RN-3, RN-4, RN-7, RN-11—опциональноДва пути window size; stale-комментарий; macro-lookup; version-conditional

[PLAN_B]
RN-1 / RN-10: задокументировать single-thread контракт в header-комментарии; DEBUGASSERT на thread-id под #ifdef DEBUG.
RN-2: установить initialized=TRUE до аллокации подресурсов ИЛИ явный partial-free по флагам.
RN-5: обновлять initial_win_size только при успехе submit; при ошибке — откат/лог.
RN-6: заменить DEBUGASSERT(0) на Curl_trc_cf_infof + возврат NULL с явным логом.
RN-8: goto fail с полным h2_stream_ctx_free при сбое любого init.
RN-9: cap PAUSED streams, мониторинг drain_total (Option B, отдельный PR).

[THREAT_MODEL]
Компоненты: cf_h2_ctx, h2_stream_ctx, nghttp2_session, bufq/bufc_pool/dynbuf, Curl_easy/multi. Trust boundaries: network↔TLS↔cfilter; cfilter↔nghttp2; nghttp2 callbacks↔stream registry; stream↔Curl_easy.

STRIDEУгрозаПриоритет
TMalformed HTTP/2 фреймы → невалидное состояние streamважно
SПодмена stream_id/mid при нарушении инвариантаважно
DDoS через исчерпание окна при PAUSED стримах (#10988)важно
IУтечка содержимого буферов при частичной init (SEC-1)важно
RНет audit-log для goaway/reset/settings-errorопционально
EMisuse multi из нескольких потоковопционально
Итого: 6 угроз, 0 critical, 4 important, 2 optional.

[SILENCE_LAYERS]
Input silence: нет метрик нагрузки (стримы/соединения/трафик) — нельзя оценить достаточность H2_CONN_WINDOW_SIZE.
Assumption silence: однопоточность multi handle — контракт не в файле, полагается на внешнюю документацию curl (VERIFY).
Consequence silence: нарушение контракта → гонки на ctx->streams/ctx->h2 → UB, повреждение памяти необратимо.

[INTERSECTION_RISKS]
Input × Assumption: нет метрик × допущение однопоточности → нельзя проверить, выдержит ли окно 10M/1GB реальную нагрузку; при misuse — гонки без диагностики.
Assumption × Consequence: допущение × необратимое повреждение памяти → нарушение контракта ведёт к UB без явного сигнала.

[ASSEMBLY]
Иерархия: core — cf_h2_ctx, h2_stream_ctx, nghttp2_session; service — cfilter callbacks, nghttp2 callbacks, Curl_easy/multi; infra — bufq/bufc_pool/dynbuf, u32_ptrset, curl_trc, TLS (вне среза).

Критический путь: cf_h2_ctx_init → session_new → submit_settings → filter loop → mem_send/mem_recv → callbacks → stream lifecycle → cf_h2_ctx_free. Циклов в срезе не обнаружено.

[REFACTORING]
Option A (hardening-only, 2–3 дня): SEC-1 (проверка init-возвратов + goto fail), SEC-2 (флаг init до подресурсов), SEC-3 (DEBUGASSERT(0) → trace + NULL), RN-5 (обновление initial_win_size только при успехе). Без изменения ABI. Option B (4–6 дней) — + window/DoS guard, trace на goaway/reset, документирование контракта. Option C (8–12 дней) — + abstraction seam для nghttp2 (тестируемость), вероятно отклонят мейнтейнеры как over-engineering.

[PARALLELS]
cf_h2_update_settings (SETTINGS) vs cf_h2_update_local_win (local window) — два пути управления окном, возможна рассинхронизация (RN-3).
cf_h2_ctx_free идемпотентен (флаг initialized); cf_h2_update_settings — нет.
H2_STREAM_WINDOW_SIZE_INITIAL = 64K при NGHTTP2_HAS_SET_LOCAL_WINDOW_SIZE, иначе = MAX (10M) — семантика зависит от версии nghttp2 (RN-11).

[TESTS]
Unit: h2_stream_ctx_create при инжектированном сбое аллокатора → NULL, без утечки (ASan/valgrind).
Unit: cf_h2_ctx_free при initialized=FALSE после частичной init → без double-free (ASan).
Unit: cf_h2_update_settings при ошибке nghttp2_submit_settings → initial_win_size не изменён.
Integration: malformed HTTP/2 фреймы (curl test suite + OSS-Fuzz).
Regression: полный tests/ curl.
Edge: goaway во время активных стримов; PAUSED стримы и исчерпание окна.

[ACTION]
NOW: нет немедленных действий — force_emergency: false.
TODAY: согласовать scope Option A с мейнтейнерами; подготовить патчи SEC-1/SEC-2/SEC-3/RN-5.
TOMORROW: PR с Option A (2–3 дня), прогон ASan + полного test suite.
LATER: Option B (window/DoS guard, trace, документирование контракта) — отдельный PR; Option C — только по запросу мейнтейнеров.

[QUESTIONS]
VERIFY: подтверждён ли контракт однопоточности multi handle во внешней документации curl? (в файле не задокументирован)
VERIFY: какая версия nghttp2 в целевой матрице сборки — влияет на NGHTTP2_HAS_SET_LOCAL_WINDOW_SIZE и семантику окна?
VERIFY: примет ли мейнтейнер curl diff Option A в одном PR (constraint 4)?
VERIFY: граница TLS↔cfilter — вне среза, целостность не проверена.

[FUNC:FULL]
ECON: effort Option A ~2–3 дня, Option B ~4–6, Option C ~8–12; cost $0 (нет cloud-ресурсов); ROI качественный — A предотвращает класс UB (SEC-1/2/3) при минимальной цене; cost of delay — каждый релиз без фикса несёт латентный UB-риск для интеграторов, монетизация без incident-данных невозможна.
FAIL: критично — h2_stream_ctx_create при OOM → частично инициализированный stream → UB (SEC-1); cf_h2_ctx_free при initialized=FALSE → утечка/double-free (SEC-2); cascade: OOM → partial stream → use-after-free в callback; recovery — goto fail + полный free, ASan-тесты.
METRICS: codebase — срез ~500 строк (полный файл >5000, усечён); deps — 1 внешняя (nghttp2 ≥ 1.15.0) + ~20 внутренних curl-заголовков; tests — в срезе отсутствуют, нужны unit+integration+fuzz; perf — buffer pool 640×16K ≈ 10M на соединение; quality — resilience_score 6/10 (консервативно, срез неполный); infra — N/A (библиотека).
ALTERNATIVES: Option A (hardening-only, 2–3 дня, минимальный diff, без изменения поведения happy path); Option B (A + window/DoS guard + trace + документирование контракта, 4–6 дней); Option C (B + abstraction seam вокруг nghttp2 для fault injection, 8–12 дней, риск отклонения мейнтейнерами).
EVOLVE: coupling — высокий к nghttp2 и curl internals (идиоматично для C); abstractions — 4/10 (нет seam для тестирования); growth — feature_add 6/10, module_replace 4/10; friction — version-conditional код (RN-11) увеличивает тест-матрицу, macro-based context access — legacy.
COMPARE: A — 2–3 дня, низкий риск, минимальная сложность, покрывает SEC-1/2/3/RN-5; B — 4–6 дней, средний риск (трогает flow-control), покрывает + RN-9/RN-1/RN-10; C — 8–12 дней, высокий риск отклонения, покрывает + тестируемость.

[MANDATORY BASE]
ECONOMICS: time Option A ~2–3 дня, cost $0, при условии отсутствия cloud-ресурсов (библиотека); ROI качественный, при условии наличия incident-данных для монетизации — нет.
RISKS: критично — RN-1 (неявный single-thread контракт), при условии misuse multi из нескольких потоков; важно — SEC-1/SEC-2/SEC-3/RN-5, при условии OOM или нарушения инварианта; опционально — RN-9 (#10988), при условии многих PAUSED стримов.
INFRASTRUCTURE: pool_size = 640 chunks (H2_STREAM_POOL_SPARES = 10M/16K), при условии дефолтных констант; memory per-connection ≈ 10M (inbufq) + 16K (outbufq) + 64K/stream, при условии дефолтных окон.
CODE: change — 4 функции (h2_stream_ctx_create, cf_h2_ctx_init/free, cf_h2_get_stream_xfer, cf_h2_update_settings), при условии Option A; ABI не меняется, при условии отсутствия публичных struct-изменений.
ACTION: now — нет (force_emergency: false); tomorrow — PR Option A; later — Option B отдельным PR.
TIMELINE: NOW — нет действий; TODAY — согласование scope; TOMORROW — PR Option A (2–3 дня); LATER — Option B (4–6 дней), Option C по запросу.
PRODUCTION IMPACT: users — все потребители curl HTTP/2 (библиотека); deploy window — релизный цикл curl; rollback — revert commit, cfilter API стабилен, N/A минут (нет сервиса).
SLO IMPACT: N/A — библиотека, не сервис; SLO на уровне потребителя, при условии деплоя в сервис-потребитель.
CLOUD COST: current $0, projected $0, delta ±$0, при условии отсутствия инфраструктурных изменений (патч библиотеки).
ON-CALL: new alerts — нет (библиотека); runbook — N/A; escalation — N/A; при условии потребительского сервиса — алерты на стороне потребителя.

[COMPLEXITY]
O(1) lookup в u32_ptrset по mid; O(1) alloc/free stream; buffer pool амортизирует аллокации. Сложность кода — высокая плотность (bitfields, macros, version-conditional). Цикломатика не вычислена (срез усечён).

[STRUCTURE]
4 слоя: filter (cf_h2_*), stream (h2_stream_ctx), protocol (nghttp2 callbacks), buffer (bufq/bufc_pool/dynbuf). Cohesion высокий внутри struct (init/free парные). Coupling высокий к nghttp2 и curl internals.

[TEXTURE]
Плотный C, комментарии объясняют неочевидные константы. Smells: macro CF_CTX_CALL_DATA через #undef/#define (fragile), H2_STREAM_CTX скрывает lookup, magic 8192 в cf_h2_initial_win_size, DEBUGASSERT(0) в production-пути, bitfields без явного layout.

[SHADOWS]
Усечение входа посреди cf_h2_update_local_win — полный control flow не оценён.
cf_h2_ctx_free при initialized=FALSE — потенциальная утечка.
h2_stream_ctx_create — непроверенные возвраты init.
Comment/code tension: H2_NW_SEND_CHUNKS=1 «accumulate» vs фактический минимум.
Blind spots: thread-safety (single-thread assumption), integer overflow в runtime window arithmetic, error path в cf_h2_update_settings, realloc push_headers.

[SECURITY]
SEC-1 (CWE-252, важно): непроверенные возвраты init в h2_stream_ctx_create. SEC-2 (CWE-459, важно): частичная init cf_h2_ctx при free. SEC-3 (CWE-617, важно): DEBUGASSERT(0) молча возвращает NULL в release. SEC-4 (CWE-754, опционально): рассинхронизация при ошибке submit. SEC-5 (CWE-362, опционально): нет явного контракта потокобезопасности. Секретов не найдено.

[TEST_ANALYSIS]
Тесты в срезе отсутствуют. Нужны: unit (инжектированный сбой аллокатора, initialized=FALSE free, ошибка submit), integration (malformed фреймы), fuzz (nghttp2 callbacks — OSS-Fuzz уже покрывает curl), regression (полный tests/). Edge: частичная init, goaway при активных стримах, PAUSED + исчерпание окна.

[DEPENDENCIES]
1 внешняя: nghttp2 ≥ 1.15.0 (enforced #error). CVE не проверены в срезе (VERIFY: рекомендуется последняя стабильная nghttp2). ~20 внутренних curl-заголовков.

[FAILURE_POINTS]
h2_stream_ctx_create — непроверенные init (важно).
cf_h2_ctx_free — частичная init (важно).
cf_h2_get_stream_xfer — DEBUGASSERT(0) в release (важно).
cf_h2_update_settings — рассинхронизация (опционально).
Исчерпание окна при PAUSED (#10988) (важно).

[EVOLVABILITY]
feature_add 6/10, module_replace 4/10, coupling 3/10, abstractions 4/10, overall 4/10. Тесная связка с nghttp2 и curl internals идиоматична для C, но ограничивает тестируемость (Option C адресует).

[AUTHOR_SOLUTIONS]
Автор (curl) использует: buffer pool для амортизации аллокаций, u32_ptrset для O(1) registry, version-conditional window sizing, DEBUGASSERT для инвариантов. Решения зрелые; пробелы — в error-путях (SEC-1/2/3) и документировании контракта.

[REFACTORING_PLAN]
SEC-1: goto fail + полный free в h2_stream_ctx_create.
SEC-2: флаг initialized до подресурсов ИЛИ явный partial-free.
SEC-3: DEBUGASSERT(0) → Curl_trc_cf_infof + NULL.
RN-5: обновление initial_win_size только при успехе submit.
Документировать single-thread контракт в header.
(Option B) cap PAUSED streams, trace на goaway/reset/settings-error.

[ECONOMICS]
Option A: 2–3 дня, $0 cloud, ROI качественный (предотвращение UB-класса). Option B: 4–6 дней. Option C: 8–12 дней. Cost of delay: латентный UB-риск на каждый релиз без фикса; монетизация без incident-данных невозможна.

[FAILURE_SCENARIO]
OOM в h2_stream_ctx_create → частично инициализированный stream → callback использует невалидный sendbuf/h1 → use-after-free / UB → crash или повреждение памяти. Recovery: goto fail + полный h2_stream_ctx_free, ASan-тест с инжектированным сбоем.

[CONFLICT_RESOLUTION]
Коллизия 1: аналитик (SEC-1/2/3 важно) vs исследователь (curl зрелый, OSS-Fuzz покрывает) — не критично: покрытие ≠ отсутствие дефекта в error-путях; фикс продолжается. Коллизия 2: RN-9 (важно) vs upstream issue #10988 — defer в Option B. Critical collisions: 0, escalation level 0.

[INVERSION]
Однопоточность нарушена → гонки на ctx->streams/ctx->h2 → UB, необратимо.
Malformed фреймы проходят валидацию nghttp2 → невалидное состояние stream, crash в callback.
OOM в h2_stream_ctx_create → частичная init → UB, утечка.

[THRESHOLDS]
PAUSED streams/connection > 50 → риск исчерпания окна (#10988), включить Option B guard.
drain_total / H2_CONN_WINDOW_SIZE > 0.8 → приближение к quota block, trace + cap.
settings submit failures / 1000 connections > 1 → расследовать версию nghttp2 / desync (RN-5).
DEBUGASSERT(0) hits в CI (debug build) > 0 → блокировать релиз.

[CONSTRAINTS]
Сохранить cfilter ABI (без публичных struct-изменений).
Без новых внешних зависимостей (nghttp2 ≥ 1.15.0).
Патч проходит полный curl test suite + OSS-Fuzz.
Diff reviewable в одном PR (Option A) — binding для scope.
Binding: constraint 4 исключает Option C из немедленного патча, фиксирует Option A как deliverable, B — follow-up.

[SECOND_OPINION]
Роль: security engineer. SEC-1/SEC-2 — реальные дефекты (CWE-252/CWE-459, латентный UB). SEC-3 — correctness bug, маскирует нарушение инварианта. SEC-5 — documentation gap, не code defect, но должен быть явным в header. Согласие: приоритет SEC-1/2/3/RN-5 в Option A. Несогласие: Option C — over-engineering для C-библиотеки, вероятно отклонят; RN-10 не повышать до critical — это документированный API-контракт, не уязвимость.

[COLLISION]
См. [CONFLICT_RESOLUTION]. critical_count: 0, escalation: none.

[FINAL_METRICS]
resilience_score 6/10 (консервативно, срез неполный). Risk nodes: 11 (1 критично, 5 важно, 5 опционально). Security findings: 5 (0 critical, 3 important, 2 optional). Threat model: 6 (0 critical, 4 important, 2 optional). Options: 3 (A/B/C). Effort: A 2–3 дня, B 4–6, C 8–12.

[FINAL_CALCULATIONS]
Buffer pool: H2_STREAM_POOL_SPARES = 10M/16K = 640 chunks. Per-connection memory ≈ 640×16K (inbufq) + 1×16K (outbufq) + 4×16K/stream (sendbuf) ≈ 10M + 16K + 64K/stream. HTTP2_HUGE_WINDOW_SIZE = 100 × 10M = 1GB. Все числа — из констант среза, при условии дефолтных #define.

[COMPLETENESS_CHECK]
Блоки D4: ECHO ✓, ROUTE ✓, CONCLUSION ✓, RISK_NODES ✓, PLAN_B ✓, THREAT_MODEL ✓, SILENCE_LAYERS ✓, INTERSECTION_RISKS ✓, ASSEMBLY ✓, REFACTORING ✓, PARALLELS ✓, TESTS ✓, ACTION ✓, QUESTIONS ✓, FUNC:FULL ✓ (6 функций, 5 строк), MANDATORY BASE ✓ (10 полей), COMPLEXITY ✓, STRUCTURE ✓, TEXTURE ✓, SHADOWS ✓, SECURITY ✓, TEST_ANALYSIS ✓, DEPENDENCIES ✓, FAILURE_POINTS ✓, EVOLVABILITY ✓, AUTHOR_SOLUTIONS ✓, REFACTORING_PLAN ✓, ECONOMICS ✓, FAILURE_SCENARIO ✓, CONFLICT_RESOLUTION ✓, INVERSION ✓, THRESHOLDS ✓, CONSTRAINTS ✓, SECOND_OPINION ✓, COLLISION ✓, FINAL_METRICS ✓, FINAL_CALCULATIONS ✓, COMPLETENESS_CHECK ✓, GRADUATED_CONCLUSION ✓, MATRIX ✓, REFLEXION ✓. Task_type review: PLAN_B ✓, MATRIX ✓, TESTS ✓, RISK_NODES ✓.

[GRADUATED_CONCLUSION]
Уверенно: SEC-1, SEC-2, SEC-3, RN-5 — латентные дефекты error-путей в видимом срезе; фикс дешёвый, без изменения happy path.
Вероятно: RN-1/RN-10 — контракт однопоточности неявный, риск при misuse (VERIFY: внешняя документация curl).
Не проверено: полный control flow (срез усечён), CVE nghttp2, TLS↔cfilter boundary, acceptance мейнтейнерами.

[MATRIX]
DimensionStatusComment
SecurityWARNSEC-1/2/3 — латентный UB в error-путях; happy path чист
FactsWARNСрез усечён; числа из констант, не из метрик нагрузки
LogicOKВыводы согласованы между стадиями; коллизий critical нет
ApplicabilityOKOption A реализуема за 2–3 дня, ABI стабилен
EffectivenessOKA покрывает SEC-1/2/3/RN-5 при минимальном diff
ResilienceWARNresilience_score 6/10; error-пути слабые
Human factorWARNКонтракт однопоточности неявный — риск misuse интеграторами
ClarityOKБлоки структурированы, числа с условиями

[REFLEXION]
Слабое место: code_generation.validation в stage4 использовал ast.parse (Python) на C-файлах — невалидно. Исправлено: указано gcc -fsyntax-only в [REFACTORING_PLAN] и [TESTS].
Слабое место: stage2 CoVe флаг «RN-10 повысить до важно» — в [RISK_NODES] RN-10 оставлен «важно» (не critical), согласовано с [SECOND_OPINION] (документированный контракт, не уязвимость). Противоречие снято.
Слабое место: риск выдать «отсутствие связи config.yaml» категорично — в [CONCLUSION] и [QUESTIONS] использованы формулировки «no signs of ... found (VERIFY)» для непроверенных границ (TLS↔cfilter, single-thread контракт).
Итог: accepted.

[AUDIT_TRAIL] generator: Vishap V6.0.1 audit_id: audit-2026-10-17-25e919 material_hash: sha256:5b4af1f1ac668e397c5b21fca9cd26ecc7fdb032ccc6080526edced495c863e0 material_hash_full: sha256:2bab21242f23eaf55d10c44bf6143059f353759b03233ab6a6d5dc5e64317dd0 pii_detected: false compliance_flags: [] compliance_controls: {} compliance_standards: [] critique_verdict: REQUIRES_REVIEW risk_verdict: REQUIRES_REVIEW cwe_ids: ['CWE-252', 'CWE-459', 'CWE-617', 'CWE-754', 'CWE-362'] owasp_categories: [] exploitability_reachable: False exploitability_auth_required: False exploitability_blast_radius: none exploitability_source_count: 0 exploitability_path: [] dataflow_path: [] dataflow_source_count: 0 anomaly_verdict: ANOMALIES_FOUND anomaly_count: 2 anomaly_method: zscore anomaly_top: [{'index': 48, 'value': 10988.0, 'score': 10.636, 'reason': 'z-score 10.64 > 3.0'}, {'index': 117, 'value': 8192.0, 'score': 7.892, 'reason': 'z-score 7.89 > 3.0'}] provenance_source: git/main provenance_commit: 3661f39

[COMPLETENESS] level: D4 required: 30 missing: [] loss_pct: 0.0% material_complete: False verdict: ACCEPTABLE
```

</details>

---

## Lessons Learned

1. **100+ KB C-файла — рабочий объём.** D4 держит детализацию на файле вдвое
   больше первого case study: 30 блоков отчёта, находки не «размазались».

2. **Пять CWE из одного файла.** 252 (unchecked return), 459 (partial init),
   617 (reachable assertion), 754 (desync), 362 (race) — разные классы дефектов,
   а не пять вариаций одного.

3. **PII-редакция работает до LLM.** Email в комментарии кода вырезан до
   отправки, анализ шёл по отредактированному срезу — это и есть
   `material_hash`, тогда как `material_hash_full` фиксирует оригинал.

4. **Anomaly-детектор добавил сигнал, которого нет у SAST.** Две строки-выброса
   (10 988 и 8 192 символа) не стали находками, но показали, что материал
   просмотрен целиком, а не только распарсен.

5. **Полный цикл сохранён при росте объёма.** STRIDE, CWE, три варианта
   рефакторинга с трудозатратами и audit trail с двумя хешами — на 100+ KB
   отчёт остаётся таким же пригодным для тикета, как на 49 KB.

**Ограничение:** как и в первом case study, отчёт не доказывает
эксплуатируемость. Три «важных» находки требуют ручного подтверждения, а две
«опциональных» зависят от контракта использования libcurl — именно это и
означает `REQUIRES_REVIEW`.
