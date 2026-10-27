# FAQ - Vishap V5.8

**Ответы на частые вопросы.**

---

## Какой LLM использует Vishap и куда уходит материал?

**Один интерфейс.** Все стадии идут через OpenAI-совместимый endpoint (`CUSTOM_LLM_URL`, `CUSTOM_LLM_KEY`, `CUSTOM_LLM_MODEL`). По умолчанию это Claude (api.anthropic.com); DeepSeek, OpenAI, Groq, OpenRouter и локальный Ollama подключаются тем же способом.

**Приватность.** Материал проходит PII-редакцию и затем уходит провайдеру, которого настроил оператор (или который выбрал вызывающий со своим ключом). На машине материал остаётся только с локальным endpoint, например Ollama. В публичном демо материал уходит на сервер и дальше провайдеру.

**Качество.** На SARD-кейсах (STONESOUP CWE-129B) модель находит CWE-129 + CWE-787 + doc/code drift.

**Если нужна другая модель:** смените `CUSTOM_LLM_URL` и `CUSTOM_LLM_MODEL` в `.env` или выберите провайдера в UI. Для Claude 5.x добавьте `CUSTOM_LLM_SEND_TEMPERATURE=false`.

## Почему 6 стадий, а не одна?

**Разделение ответственности:**

| Stage | Роль | Не делает |
|-------|------|-----------|
| 0 Orchestrator | Route, level, task_type | Не анализирует |
| 1 Scanner | 4 слоя, стек | Не находит риски |
| 2 Analyst | Risk nodes, STRIDE | Не пишет отчёт |
| 3 Researcher | Industry parallels | Не синтезирует |
| 4 Synthesizer | Options, refactoring | Не форматирует |
| 5 Transmitter | Markdown | Не анализирует |

**Одна стадия** = смешение всего -> хуже качество, труднее debug.

## Почему AGPL, а не MIT?

**AGPL** - free to use, modify, distribute. **SaaS allowed**, но если Vishap - network service - нужно открыть source.

**MIT** позволяет closed-source SaaS. Для security-инструмента AGPL - правильнее: transparency.

## Как масштабируется на 1000 файлов?

**Batch mode:** POST /analyze/batch с массивом materials.

**Ограничения:**
- Rate limit: 10 req/min per IP (по умолчанию)
- LLM: 40-90 сек на файл
- Параллелизм: max_concurrent 1..10 (по умолчанию 3)

**1000 файлов x 90 сек / 3 concurrent = ~8 часов.** Для больших объёмов - увеличить max_concurrent или очередь.

## Что если LLM недоступен?

**Retry:** 3 попытки, exponential backoff (2s -> 30s).

**Fallback:** провайдер один — DSH harness. Если он недоступен, pipeline возвращает ошибку с подсказкой про `HARNESS_URL` / `HARNESS_TOKEN`.

**Если LLM недоступен:** pipeline вернёт ошибку. Audit не создаётся.

**Что делать:** поднять локальный OpenAI-совместимый сервер (vLLM / LM Studio / llama.cpp) и указать `VISHAP_LLM_PROVIDER=custom` + `CUSTOM_BASE_URL`.

## Как обновляется, если появится новый CVE?

**Vishap не имеет встроенной CVE базы.** Он анализирует код - не сверяет с базой.

**Что делать:**
- Для CVE зависимостей - pip-audit, npm audit, govulncheck отдельно.
- Для CVE в коде - LLM может найти известные паттерны (Log4Shell, OpenSSL).
- Регулярно обновлять: git pull && pip install -r requirements.txt.

## Чем отличается от CodeRabbit / Qodo / Graphite?

| Tool | Что анализирует | Multi-material | Audit trail | Self-hosted |
|------|-----------------|----------------|-------------|-------------|
| CodeRabbit | Code (PR review) | Code only | No | No |
| Qodo | Code | Code only | No | No |
| Graphite | Code (PR stack) | Code only | No | No |
| Snyk | Deps + code (SAST) | Deps + code | Partial | Partial |
| Semgrep | Code (SAST) | Code only | No | Yes |
| **Vishap** | Code, config, spec, data, logs | **5 types** | **Yes (SHA-256)** | **Yes (AGPL)** |

**Где Vishap сильнее:** multi-material, audit trail, self-hosted, determinism.

**Где проигрывает:** CI-интеграция (у CodeRabbit/Graphite - готовая), SARIF output, IDE integration.

## Сколько стоит один анализ?

**LLM:** стоимость вашей модели внутри harness; на своём железе — $0 за токены.
**Инфраструктура:** $0 (если локально).
**CI:** $0 (GitHub Actions free tier).

**Сравнение с senior-аналитиком:** $800/день x 1 час = $100 за один ручной анализ. Vishap - $0.007. **14 000x дешевле.**

## Можно ли использовать локально без интернета?

**Да** — весь анализ идёт через локальный DSH harness, поэтому без интернета работает всё, кроме того, что harness сам ходит в сеть.

**Требования:** CPU/GPU, ~7B модель (llama3, qwen, deepseek-coder).

**Минусы:** 20-40 минут на файл (CPU). Slow.

**Плюсы:** приватный код не уходит в облако. Для sensitive data.

**Как:** POST /mode -> {"mode": "local"}.

## Что делать, если Vishap нашёл ложное срабатывание?

**Проверить вручную** - LLM может ошибаться.

**Использовать VERIFY-пометки** - Vishap явно помечает «не проверено».

**Сравнить с SAST** - если Semgrep/Bandit не подтверждает - вероятно FP.

**Сообщить** - GitHub issue с описанием.

---

*Last updated: 2026-10-12 | Vishap V5.8*