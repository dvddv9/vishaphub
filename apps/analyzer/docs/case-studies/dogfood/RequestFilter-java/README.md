# Case Study: RequestFilter.java (Sakai Foundation)

Dogfood-кейс: реальный production-код из Sakai LMS, прогнанный через Vishap v5.10.5 end-to-end (API + UI). **Стал триггером для v5.10.5 и v5.10.6.**

## О файле

- **Класс:** `org.sakaiproject.util.RequestFilter`
- **Источник:** Sakai Foundation (ECL 2.0 license)
- **Год:** 2005-2008
- **Размер:** 57 396 chars (обрезан до 12 000 в анализе)
- **Строк:** 221 (в слайсе)
- **Язык:** Java
- **Роль:** servlet filter -- единая точка входа всех запросов Sakai

## Метрики анализа (v5.10.5)

| Метрика | Значение |
|---|---|
| Level | **D3** (глубокий анализ) |
| Route | stage4 -> stage3 |
| Cost | **$0.007933** |
| Model | deepseek-chat |
| Material (analyzed) | 12 000 chars (truncated from 57 396) |
| Truncated | true |
| Completeness | ACCEPTABLE, loss_pct: 0.0% |

## Что Vishap нашёл

**11 risk_nodes** (3 критичных, 6 важных) + **6 угроз STRIDE**.

### Критичные risk_nodes (priority=критично)

| ID | Риск |
|---|---|
| **RN-1** | Thread-local leak при исключении в chain.doFilter |
| **RN-8** | ClusterService недоступен -> блокировка всех запросов |
| **RN-11** | Смена семантики ATTR_SESSION / cookie-атрибутов ломает SSO |

### Важные risk_nodes

- RN-2 (int-константы session mode вместо enum)
- RN-3 (двойной парсинг multipart)
- RN-5 (@SuppressWarnings на классе)
- RN-7 (DiskFileItemFactory threshold=1024)
- RN-9 (thread-local bindings без TTL)
- RN-10 (race на m_* при init)

### Security-секция (отдельно от risk_nodes)

- **SEC-1** -- session fixation через session.parameter.allow (критично)
- **SEC-4** -- upload DoS, continueOverMax (критично)
- **SEC-5** -- path traversal upload.dir (важно)
- **SEC-6** -- privilege escalation через LTI (важно)

### STRIDE

- **S** -- session fixation (SEC-1)
- **T** -- подмена cookie (SEC-3)
- **D** -- upload DoS (SEC-4)
- **I** -- утечка thread-local (RN-1)
- **E** -- path traversal (SEC-5)
- **E** -- privilege escalation (SEC-6)

### Рекомендации (PLAN_B)

- **Option A** -- Hardening in place (3-5 дней): try/finally cleanup, circuit breaker, запрет session.parameter.allow, принудительный HttpOnly+Secure+SameSite, abort при upload max.
- **Option B** -- Decompose into filter chain (10-15 дней).
- **Option C** -- Facade + strategy (7-10 дней).

Рекомендация Vishap'а: **A -> C -> B**.

## P2-7/7b/12 -- НЕ сработали (ожидаемо)

| Фича | Результат | Причина |
|---|---|---|
| **P2-7 (regex)** | exploitability_path: [] | Java не содержит Flask/JS patterns |
| **P2-7b (AST)** | dataflow_path: [] | Python-only |
| **P2-12 (anomaly)** | verdict: NORMAL, samples=22 | Код не числовой (ложная попытка) |

**Вывод:** LLM-анализ (Stage 2) -- основной движок для не-Python. P2-фичи работают только в своей области.

## Баги, найденные dogfood'ом (ОБА FIXED в v5.10.6)

### Баг 1 (критично): risk_verdict: SAFE при критичных рисках

- **Симптом:** final_markdown содержит 11 рисков (3 критичных), но audit.risk_verdict = SAFE.
- **Причина:** run_audit() вычислял risk_verdict только из pii/compliance/cwe_ids, игнорируя stage2.risk_nodes.
- **Фикс v5.10.6:** run_audit() принимает stage2_result, проверяет risk_nodes на priority in (критично, critical) -> REQUIRES_REVIEW.
- **Регрессия:** tests/test_risk_verdict.py (7 тестов).

### Баг 2 (важно): anomaly на не-числовом коде

- **Симптом:** anomaly.samples = 22, mean = 645, std = 794 на Java-коде.
- **Причина:** parse_numbers нашёл 22 числа (line numbers, hex-константы).
- **Фикс v5.10.6:** density guard (len(numbers)/len(text) < 0.01 -> {}) + INSUFFICIENT_DATA -> {}.
- **Регрессия:** tests/test_anomaly_density.py (5 тестов).

## Файлы

| Файл | Что |
|---|---|
| result_sess-2026-10-14-174403.json | Полный результат (stage0-stage4 + final_markdown) |
| audit_sess-2026-10-14-174403.json | Audit trail |
| report_sess-2026-10-14-174403.md | Markdown-отчёт (13836 chars) |
| history.json | Список анализов |

## Ссылки

- **v5.10.5 release:** https://github.com/dvddv9/vishap/releases/tag/v5.10.5
- **v5.10.6 release:** https://github.com/dvddv9/vishap/releases/tag/v5.10.6
- **Sakai Foundation:** https://www.sakaiproject.org/

## Выводы

1. **Vishap работает на production-коде.** D3, $0.008, 11 рисков.
2. **LLM-анализ -- senior-level** (INTERSECTION_RISKS, SILENCE_LAYERS, REFLEXION).
3. **P2-фичи -- узкоспециализированы.** Для Java нужен v5.11.
4. **2 бага найдено:** risk_verdict (fixed v5.10.6), anomaly (fixed v5.10.6).
5. **Первый end-to-end dogfood** через UI+API за 12 релизов.
6. **Этот кейс стал триггером** для v5.10.5 и v5.10.6.
