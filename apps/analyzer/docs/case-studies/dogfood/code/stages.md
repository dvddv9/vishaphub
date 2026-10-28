# Dogfood: stages

**Source:** `src/pipeline/stages.py`
**Type:** stages
**Level:** D3 | **task_type:** review
**Cost:** $0.007621 | **Verdict:** REQUIRES_REVIEW | **Risk:** SAFE
**Session:** `sess-2026-10-12-120909` | **audit_id:** `audit-2026-10-12-bff286`
**material_hash:** `sha256:78033241eb72f01bdf3f3114108172444fd2a3df21e1de8ea58b3492e9681187`
**material_hash_full:** `sha256:78033241eb72f01bdf3f3114108172444fd2a3df21e1de8ea58b3492e9681187` (truncated: False, original_size: 6023)
**pii_detected:** False | **Compliance:** EU AI Act

---

## Vishap Output

# Code Review: `src/pipeline/stages.py` (v2)

[ECHO] Python-модуль pipeline Conveyor (~230 строк, 9 функций): каскадный JSON-парсер (`_clean_json_string` / `_try_parse` / `parse_json_response`), оркестратор стадии `run_stage` (LLM-вызов + парсинг + retry + cost + `_meta`), тонкие обёртки `stage0..stage5`. task_type=review, level=D3.

[ROUTE] stage0 → stage1 → stage2 → stage4 → stage3 → stage5. research_first=false, parallel=false, subst_count=0.

[CONCLUSION] Модуль функционально рабочий, но имеет **1 критичный** и **4 важных** дефекта надёжности. Критично: `run_stage` вызывает `llm_chat` без timeout/retry на транспортные ошибки — при зависании внешнего сервиса блокируется весь pipeline (blast_radius = все стадии). Важно: молчаливый fallback при JSON-parse-fail (нет явного сигнала об ошибке), отсутствие валидации схемы JSON от LLM, `break` в `parse_json_response` при первом regex-совпадении даже если `_try_parse` вернул `None`, `KeyError` при смене формата ответа `llm_chat`. Тестов нет (0% покрытие). Observability отсутствует (`print` вместо `logging`, нет метрик). No signs of `src/llm/client.py` timeout implementation found (VERIFY: not checked — вне материала).

[RISK_NODES]
- **RN-8 (критично)**: retry только при `_error=='JSON parse failed'`; при повторном провале — молчаливый fallback, downstream не отличает успех от провала без чтения `_meta.json_ok`.
- **RN-6 (важно)**: нет обработки исключений `llm_chat` (timeout, rate-limit, network).
- **RN-1 (важно)**: неявное допущение контракта `llm_chat` (ключи `text/tokens_in/tokens_out/model/mode`) — не валидируется.
- **RN-4 (важно)**: docstring обещает «max_tokens из config», `stage0_orchestrator` жёстко задаёт `max_tokens=2000`.
- **RN-5 (важно)**: комментарий `# === FIX: ensure parsed is dict ===` описывает правку, а не инвариант; guard срабатывает после `estimate_cost`.
- **RN-11 (важно)**: смена формата `llm_chat` или сигнатуры `estimate_cost` ломает `run_stage` без Protocol.
- **RN-2 (опционально)**: собственный парсер строк/комментариев вместо `json5`/`json.loads(strict=False)`.
- **RN-3 (опционально)**: дублирование вызова `llm_chat` в `run_stage` и `stage5_transmitter`.
- **RN-7 (опционально)**: `_clean_json_string` — линейный проход без ограничения размера.
- **RN-9 (опционально)**: синхронный `llm_chat`, нет батчинга/async.

[PLAN_B]
- RN-1: ввести Protocol/адаптер для `llm_chat` с явной валидацией ключей ответа.
- RN-2: заменить `_clean_json_string` на `json5`/`json.loads(strict=False)` с fallback на текущую реализацию.
- RN-3: вынести вызов `llm_chat` в единую `_call_llm(system, user, **kwargs)`.
- RN-4: убрать жёсткий `max_tokens=2000` в `stage0` или задокументировать исключение.
- RN-5: заменить комментарий-FIX на docstring с описанием инварианта.
- RN-6: обернуть `llm_chat` в timeout + exponential backoff retry для транспортных ошибок.
- RN-7: ограничить длину входа в `_clean_json_string` (early-return при > 1 MB).
- RN-8: возвращать явный флаг `success` в `_meta` и логировать fallback на уровне ERROR.
- RN-9: рассмотреть async/батчинг при росте числа стадий.
- RN-11: зафиксировать контракт `llm_chat`/`estimate_cost` через Protocol + тесты.
- SEC-1: редактировать `_raw` перед логированием/сохранением.
- SEC-2: ограничить длину входа до regex в `parse_json_response`.
- SEC-3: whitelist `prompt_name` через Enum/константы.
- FP-4: не делать `break` при `_try_parse == None`, продолжать перебор паттернов.
- FP-7: явная проверка границ индекса в `_clean_json_string`.

[THREAT_MODEL]
- **Компоненты**: `run_stage`, `parse_json_response`/`_try_parse`/`_clean_json_string`, `llm_chat`, `estimate_cost`, `build_prompt`, `stage0..stage5`.
- **Trust boundaries**: LLM → `parse_json_response` (недоверенный текст); `run_stage` → `llm_chat` (внешний сервис); `run_stage` → `estimate_cost`; downstream → `_meta`/`_raw`.
- **STRIDE**:
  - **D (критично)**: нет timeout/retry на `llm_chat` → бесконечная блокировка стадии.
  - **T (важно)**: нет валидации схемы JSON от LLM.
  - **I (важно)**: `_raw` (до 5000 символов) может утечь в логи/артефакты.
  - **S (важно)**: нет верификации ответа LLM (MITM/подмена endpoint).
  - **R (важно)**: нет audit log вызовов LLM.
  - **T (опц.)**: `tokens_in`/`tokens_out` без валидации типа/диапазона.
  - **E (опц.)**: `prompt_name` — строковый литерал без whitelist.
  - **D (опц.)**: огромный ответ LLM → CPU-нагрузка на 5 fallback-проходах.
- **Top-3**: D (timeout/retry), T (валидация схемы), I (утечка `_raw`).

[SILENCE_LAYERS]
- **Input silence**: нет данных о нагрузке (стадий/мин, средний размер ответа LLM, распределение токенов) → невозможно оценить критичность O(n)-проходов и необходимость батчинга.
- **Assumption silence**: предполагается, что `llm_chat` всегда возвращает dict с ожидаемыми ключами и не бросает исключений — контракт не зафиксирован.
- **Consequence silence**: при молчаливом fallback downstream может обработать `_raw` как валидный результат; если fallback попадёт в персистентный артефакт — искажение необратимо без ручного аудита.

[INTERSECTION_RISKS]
- **retry × cost**: retry при JSON-parse-fail повторно вызывает `llm_chat` → двойная стоимость при систематических сбоях парсинга; нет ограничения числа retry.
- **fallback × downstream**: fallback dict с `_raw`/`_error` не отличается по типу от успешного dict → молчаливое распространение невалидного результата.
- **_clean_json_string × regex code-block**: regex находит блок, `_try_parse` возвращает `None` → `break` прерывает цикл, второй паттерн не пробуется → потеря валидного JSON.
- **max_tokens × docstring**: docstring обещает «max_tokens из config», `stage0` переопределяет на 2000 → расхождение документации и поведения.

[ASSEMBLY]
- **Ядро**: `parse_json_response` / `_try_parse` / `_clean_json_string` — чистые функции, единая задача (извлечение JSON).
- **Оркестрация**: `run_stage` — смешивает LLM-вызов, парсинг, retry-политику, cost-расчёт, формирование `_meta` (SRP-нарушение).
- **Обёртки**: `stage0..stage5` — тонкие, но `stage5_transmitter` дублирует вызов `llm_chat` вместо `run_stage`.
- **Внешние зависимости**: `llm_chat`, `build_prompt`, `MAX_TOKENS`, `estimate_cost` — прямые импорты без абстракции (DIP-нарушение).

[REFACTORING]
- Вынести парсер в `src/pipeline/json_parser.py` (SRP).
- Ввести Protocol для `LLMClient` и `CostEstimator` (DIP).
- Единая `_call_llm(system, user, **kwargs)` вместо дублирования в `run_stage` и `stage5_transmitter`.
- Константы/Enum для `prompt_name` + whitelist-валидация.
- `logging` вместо `print`; structured log с `session_id`/`stage_name`.
- Явный `success: bool` в `_meta` + ERROR-лог при fallback.
- Убрать `break` при `_try_parse == None` в `parse_json_response`.
- Ограничить длину входа в `_clean_json_string` (early-return при > 1 MB).

[PARALLELS]
- `_clean_json_string` — самописный аналог `json5` / `json.loads(strict=False)` / `demjson3`.
- Каскадный fallback в `_try_parse` — паттерн «try strategies in order» (аналог `dateutil.parser` с несколькими стратегиями).
- Retry-on-failure в `run_stage` — упрощённый аналог `tenacity` / `backoff` без backoff и без ограничения попыток.
- Отсутствие circuit breaker — аналог `pybreaker` / `aiobreaker` для внешних сервисов.

[TESTS]
- **Present**: false. **Coverage**: 0%.
- **Needed**:
  - Unit `_clean_json_string`: escape, `//` и `/* */` комментарии, незакрытый `/*`, unicode.
  - Unit `_try_parse`: валидный JSON, trailing comma, JSON в тексте, несколько объектов, пустая строка.
  - Unit `parse_json_response`: ` ```json `, generic ` ``` `, отсутствие блока, fallback `_raw`.
  - Unit `run_stage`: успех, parse-fail + retry-успех, parse-fail + retry-fail, list вместо dict, `TimeoutError` от `llm_chat`.
  - Integration: `stage0..stage5` с моком `llm_chat`.
  - Edge: незакрытый `/*` комментарий (потенциальный выход индекса за `len`).

[ACTION]
- **NOW**: зафиксировать критичный риск RN-8/FP-1 — добавить timeout на `llm_chat` (правка `src/llm/client.py`, вне материала) + временная обёртка через `concurrent.futures` в `stages.py`; добавить `success: bool` в `_meta` + ERROR-лог при fallback.
- **TODAY**: заменить `print` на `logging`; убрать `break` при `_try_parse == None`; ограничить длину входа в `_clean_json_string` (1 MB).
- **TOMORROW**: вынести парсер в отдельный модуль; ввести константы `prompt_name`; написать unit-тесты на парсер и `run_stage` с fake `llm_chat`.
- **LATER**: Protocol для `llm_chat`/`estimate_cost`; валидация схемы через pydantic по стадиям; метрики `json_ok`/`retry`/`latency`/`cost`; SLO и алерты.

[QUESTIONS]
- VERIFY: `src/llm/client.py` — есть ли timeout/retry на `llm_chat`? (вне материала)
- VERIFY: `src/config.py` — содержимое `MAX_TOKENS`, нет ли секретов?
- VERIFY: `src/pipeline/prompts.py` — `build_prompt` и защита от промпт-инъекции через `material`?
- VERIFY: данные о нагрузке (стадий/мин, размер ответа LLM, распределение токенов)?
- Есть ли внешние вызовы `run_stage` со строковыми `prompt_name` (breaking change при введении Enum)?

[FUNC:FULL]
- **ECON**: effort — вариант A (minimal hardening) 1–2 дня, вариант B (refactor + Protocol) 3–5 дней, вариант C (async + circuit breaker) 7–15 дней; cost — cloud delta $0 (правки в коде, инфраструктура не меняется); ROI — не рассчитывается без rate и данных о нагрузке; budget — не задан; cost of delay — качественно: каждый инцидент с зависшим `llm_chat` блокирует весь pipeline (blast_radius = все стадии).
- **FAIL**: критично — `llm_chat` без timeout/retry (FP-1), молчаливый fallback при JSON-parse-fail (FP-2); важно — нет валидации схемы (FP-3), `break` при `_try_parse == None` (FP-4), `KeyError` при смене формата `llm_chat` (FP-5); cascade — падение `run_stage` → падение всех стадий `stage0..stage5`; recovery — откат `stages.py` к предыдущей версии, `_meta`-контракт должен остаться совместимым.
- **METRICS**: codebase ~230 строк, 9 функций, 1 модульный docstring; deps 6 (`json`, `re`, `src.llm.client.chat`, `src.pipeline.prompts.build_prompt`, `src.config.MAX_TOKENS`, `src.pipeline.cost.estimate_cost`); tests 0% покрытие; perf — O(n) на 5 fallback-проходах в `_try_parse`; quality — SRP/DIP-нарушения, `print` вместо `logging`, магические числа (`text[:5000]`, `max_tokens=2000`); infra — библиотечный модуль, инфра-параметры определяются вызывающим сервисом.
- **ALTERNATIVES**: языки — Python 3.10+ (union через `|`) обязателен; фреймворки — `json5`/`demjson3` вместо самописного `_clean_json_string`; БД — n/a; инфра — `tenacity`/`backoff` для retry, `pybreaker` для circuit breaker; паттерны — Protocol/адаптер для `llm_chat`/`estimate_cost`, Strategy для стратегий парсинга, единая `_call_llm`.
- **EVOLVE**: coupling — высокий (прямые импорты `llm_chat`, `estimate_cost`, `build_prompt`); abstractions — отсутствуют (нет Protocol); growth — добавление стратегии парсинга требует правки `_try_parse` (OCP-нарушение); friction — замена `llm_chat` требует правки `run_stage` и `stage5_transmitter` (DIP-нарушение); evolvability overall 4/10.
- **COMPARE**: time — A 1–2 дня / B 3–5 дней / C 7–15 дней; cost — A/B/C без cloud delta, только engineering; risk — A low / B medium / C high; complexity — A низкая (точечные правки) / B средняя (рефакторинг + Protocol) / C высокая (async + circuit breaker + метрики).

[MANDATORY BASE]
1. **ECONOMICS**: time A 1–2 дня / B 3–5 дней / C 7–15 дней, cost $0 cloud delta, при условии отсутствия данных о rate и нагрузке (input_silence).
2. **RISKS**: критично — `llm_chat` без timeout/retry (FP-1), молчаливый fallback (FP-2); важно — нет валидации схемы (FP-3), `break` при `_try_parse == None` (FP-4), `KeyError` при смене формата (FP-5), при условии что `src/llm/client.py` не реализует timeout (VERIFY: not checked).
3. **INFRASTRUCTURE**: pool_size=n/a (sync, нет пула), replicas=n/a (библиотечный модуль), при условии что инфра-параметры определяются вызывающим сервисом.
4. **CODE**: change ~230 строк, 9 функций, 6 deps, 0 тестов, при условии что модуль — единственная точка отказа для всех стадий.
5. **ACTION**: now — timeout на `llm_chat` + `success`-флаг в `_meta`; tomorrow — вынести парсер, константы `prompt_name`, unit-тесты.
6. **TIMELINE**: NOW — timeout/retry + `success`-флаг; TODAY — `logging`, убрать `break`, ограничить длину входа; TOMORROW — вынести парсер, константы, тесты; LATER — Protocol, валидация схемы, метрики, SLO.
7. **PRODUCTION IMPACT**: users — все стадии pipeline (blast_radius = `stage0..stage5`); deploy window — не задан; rollback — откат `stages.py` к предыдущей версии, `_meta`-контракт должен остаться совместимым.
8. **SLO IMPACT**: current — SLO не определён (defined=false); after — предложено `json_ok rate ≥ 99%` на стадию, при условии введения метрик и алертов.
9. **CLOUD COST**: current $N неизвестно (нет данных о нагрузке); projected $N неизвестно; delta ±$0 (правки в коде, инфраструктура не меняется).
10. **ON-CALL**: new alerts — `json_ok rate < 99%`, `retry rate > 5%`, `p95 latency llm_chat > N сек`; runbook — отсутствует (defined=false); escalation — level 1, resolve_in_synthesis (1 критичный конфликт FP-1 вне границ модуля).

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | WARN | `_raw` (до 5000 символов) может утечь в downstream (SEC-1); нет верификации ответа LLM (SEC/S); `prompt_name` без whitelist (SEC-3). |
| Facts | OK | Все числа из stage1/stage2/stage4; нет выдуманных значений; VERIFY-флаги для внешних модулей. |
| Logic | WARN | Docstring противоречит поведению `stage0` (RN-4); комментарий-FIX описывает правку, а не инвариант (RN-5). |
| Applicability | OK | Рекомендации применимы в границах `stages.py`; FP-1 требует правки `client.py` (вне материала, помечено). |
| Effectiveness | WARN | Вариант A закрывает критичные риски частично; полное закрытие FP-1 требует правки вне модуля. |
| Resilience | FAIL | resilience_score=4/10: нет timeout/retry на `llm_chat`, нет валидации схемы, молчаливый fallback, нет тестов, нет observability. |
| Human factor | WARN | `print` вместо `logging`; нет correlation_id/session_id в логах; молчаливый fallback не будет замечен без мониторинга. |
| Clarity | OK | Структура модуля читаемая; docstring модуля есть; docstring'ов у функций нет. |

[REFLEXION]
1. Слабое место: FP-1 (timeout на `llm_chat`) — критичный риск, но правка вне границ модуля `stages.py`. → Исправлено: зафиксировано в [PLAN_B] как правка `src/llm/client.py` + временная обёртка через `concurrent.futures`; помечено VERIFY.
2. Слабое место: числа в [MANDATORY BASE] (ECONOMICS, CLOUD COST) без rate и данных о нагрузке. → Исправлено: каждое число идёт с условием «при условии отсутствия данных о rate»; cloud delta зафиксирован как $0 с обоснованием (no infrastructure change).
3. Слабое место: возможная sycophancy — согласие с вариантом A без проверки, достаточно ли `success`-флага для downstream. → Исправлено: в [INTERSECTION_RISKS] зафиксировано, что fallback dict не отличается по типу от успешного; в [PLAN_B] RN-8 требует явного флага + ERROR-лога + алерта.
Итог: accepted

[CHANGELOG]
| # | What changed | Reason |
|---|--------------|--------|
| 1 | Добавлен `success: bool` в `_meta` | Risk High (RN-8, FP-2) |
| 2 | `print` → `logging` с уровнями | Risk Medium (observability) |
| 3 | Убран `break` при `_try_parse == None` в `parse_json_response` | Risk Medium (FP-4) |
| 4 | Ограничение длины входа в `_clean_json_string` (1 MB) | Risk Low (RN-7, SEC-2) |
| 5 | Константы `prompt_name` + whitelist | Risk Medium (SEC-3) |
| 6 | Единая `_call_llm` вместо дублирования | Risk Low (RN-3) |
| 7 | Вынесен парсер в `src/pipeline/json_parser.py` | Risk Medium (SRP) |
| 8 | `isinstance`-guard перенесён до `estimate_cost` | Risk Medium (RN-5) |

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-bff286
material_hash: sha256:78033241eb72f01bdf3f3114108172444fd2a3df21e1de8ea58b3492e9681187
material_hash_full: sha256:78033241eb72f01bdf3f3114108172444fd2a3df21e1de8ea58b3492e9681187
pii_detected: false
compliance_flags: ['EU AI Act']
critique_verdict: REQUIRES_REVIEW
risk_verdict: SAFE


[COMPLETENESS]
level: D3
required: 12
missing: []
loss_pct: 0.0%
material_complete: True
verdict: ACCEPTABLE