# Архитектура

    spec.yaml ──► Intake ──► Design ──► Build ──► Verify ──► Deliver ──► файлы + трасса
                   R1..Rn    файлы,      модель    доказа-    гейт,
                             дыры        пишет     тельства   diff, запись
                                         код       и вердикт  откат
                                  ▲                   │
                                  └── repair (до N) ──┘

Один файл — одна ответственность. Пакет `src/generator/`:

| Папка / файл | Что делает |
|---|---|
| `tools/spec.py` | загрузка и проверка `spec.yaml`; каждая запись помнит свою строку (`Spec`, `SpecError`) |
| `pipeline/intake.py` | этап 1: требования R1..Rn с приоритетом, без модели |
| `tools/gaps.py` | дыры: `assumption`, `contradiction`, `missing_input` |
| `pipeline/design.py` | этап 2: план файлов и дыры |
| `pipeline/textcheck.py` | свободный `text` против требований (один вызов модели, только отчёт) |
| `pipeline/generate.py` | этап 3: сообщения для модели, разбор ответа, раунд исправления |
| `pipeline/build.py` | проверки сборки: `ast.parse`, `ruff`, имена тестов `test_rN` |
| `pipeline/verify.py` | этап 4: тесты модели, собственные атаки, правила по AST, покрытие, возраст spec, вердикты |
| `pipeline/sandbox.py`, `_sandbox_runner.py` | запуск кода дочерним процессом (не изоляция) |
| `tools/analyzer.py` | внешний `vishap analyze` и разбор его SARIF |
| `pipeline/deliver.py` | этап 5: гейт, diff, backup, запись, трасса, откат |
| `pipeline/orchestrator.py` | `run_pipeline`: все этапы подряд, цикл исправлений, часы стадий, история |
| `pipeline/stages.py` | реестр этапов и их промптов, `parse_json_response`, `StageClock` |
| `pipeline/verdict.py` | единственное место, где из доказательств получается вердикт |
| `pipeline/cost.py` | цена вызовов модели (цены задаёт пользователь) |
| `pipeline/batch.py` | несколько spec подряд, по папке на каждый |
| `pipeline/prompts.py` | загрузка промптов, `wrap_material()`, `build_prompt()` |
| `prompts/*.md` | все промпты (см. `prompts/README.md`) |
| `llm/` | `custom_client.py` вызов OpenAI-совместимого API, `client.py` `chat()`, `_observe.py` учёт вызовов и токенов, `providers.py` белый список провайдеров, `_scrub.py` |
| `api/` | проверка Host/Origin и токена, лимит одного прогона и лимит на адрес, задачи (`job_store*.py`, `jobs.py`), настройки модели из браузера, отчёт |
| `storage/history.py` | `<out>/.vishap/history.json` |
| `observability/logging.py` | логирование: id прогона и запроса, фильтр ключа |
| `main.py` | HTTP-сервер: форма и API |
| `cli.py` | командная строка |
| `config.py`, `version.py` | пути, пределы, переключатели окружения; версия |
| `tools/stride.py`, `tools/injection.py`, `tools/strict.py`, `tools/domains.py`, `tools/spec_text.py` | таблица STRIDE по spec; инструкции к модели в spec; STRICT; напоминания по области; тексты spec с номерами строк |
| `pipeline/effort.py`, `pipeline/candidates.py`, `pipeline/cove.py` | глубина прогона; лучший из N; сверка «что сказано в spec» и «что делает код» |
| `tools/quality_gate.py`, `tools/baseline.py` | гейт из `.vishap-generator.yml`; принятые дыры |
| `tools/static_scan.py` | правила по AST с CWE/OWASP |
| `tools/redact.py`, `tools/provenance.py` | секреты вырезаются до модели; откуда взялся прогон |
| `tools/report.py`, `tools/sarif.py`, `tools/examples.py` | отчёт Markdown; SARIF 2.1.0; примеры для формы |
| `web/index.html` | форма: один файл, без сборки |

## Аналоги в Vishap

Каждая часть сделана по той части Vishap, которая решает ту же задачу. Имена повторены, где это имеет смысл.

| Генератор | Vishap | Чем отличается |
|---|---|---|
| `pipeline/stages.py`: реестр, `parse_json_response`, `StageClock` | `pipeline/stages.py`, `_meta` стадий | оборванный JSON не чинится: обрезанный файл — неверный файл |
| `pipeline/orchestrator.py` | `run_audit` | пять стадий, цикл исправлений |
| `pipeline/verdict.py` | `verdict.py` | вердикт по коду и по spec отдельно |
| `tools/quality_gate.py`, `.vishap-generator.yml` | `tools/quality_gate.py` | ключи: `fail_on`, `coverage_min`, `stale_days`, `max_critical_gaps`, `fail_on_analyzer`, `require_coverage`, `baseline` |
| `tools/baseline.py` | `tools/baseline.py` | отпечаток дыры = тип и текст, не номер и не строка |
| `tools/static_scan.py` | `tools/static_scan.py` | два правила (`sql-from-input`, `log-raw-input`), оба с CWE |
| `pipeline/sandbox.py` | `pipeline/sandbox.py` | дочерний процесс, не изоляция |
| `llm/*`, `llm/providers.py` | `llm/*` | браузер выбирает id провайдера из списка, URL из запроса не берётся |
| `pipeline/cost.py` | `cost.py` | цены не выдуманы: из `GENERATOR_PRICE_IN/OUT` |
| `tools/redact.py` | `tools/redact.py` | только секреты; e-mail по `pii=True` |
| `tools/provenance.py` | `tools/provenance.py` | хэши spec и промптов, имя и хост модели |
| `storage/history.py` | `storage/history.py` | файл в папке вывода, не БД |
| `observability/logging.py` | `observability/logging.py` | стандартный `logging`, не structlog |
| `pipeline/batch.py` | `pipeline/batch.py` | по папке на spec, поэтому Deliver не нужно сериализовать |
| `tools/stride.py` | `threat_model` аналитика | таблица покрытия по spec, не рассказ модели; `proof` добавляет Verify |
| `pipeline/cove.py`, `prompts/04_verify_cove.md` | шаг COVE | независимый ответ модели сверяется не со вторым ответом, а с запуском кода |
| `pipeline/candidates.py` | USC (несколько проб, самая согласованная) | судья — Verify, не голосование |
| `tools/strict.py` | режим `[STRICT]`, `STRICT_MISSING_PCT` | выключен по умолчанию; называет недостающие поля |
| `pipeline/effort.py` | уровни глубины D0–D4 | три имени: quick, standard, deep |
| `tools/injection.py` | `substitution_seen` | узкие шаблоны EN/RU; spec и так идёт к модели только как данные |
| `tools/domains.py` | чек-листы областей | напоминания, не требования |
| `tools/environment.py` | — | что есть на машине Verify (Python, библиотеки из плана); модель узнаёт это до того, как пишет код |
| `pipeline/mutation.py` | мутационное тестирование (идея) | меняет код по мелочи и смотрит, заметят ли тесты модели; модель не вызывается; в deep один раунд на усиление тестов |
| `tools/questions.py` | — | дыры spec как вопросы автору, рядом с тем, что модель решила сама |
| `tools/assumptions.py` | — | комментарии `# assumption:` из кода одним списком: что модель решила сама |
| `api/job_store*.py`, `api/jobs.py` | асинхронные задачи | в памяти сервера, час |
| `api/rate_limit.py` | `api/rate_limit.py` | окно на адрес сокета; заголовкам прокси не верим |
| `tools/report.py` | `static_scan.render_markdown`, `api/reports` | один и тот же прогон даёт один и тот же текст |
| `config.validate_config` | `validate_config` | читает, ничего не меняет, ключ не печатает |
| `cli.py`: `info`, `history`, `batch`, `baseline` | одноимённые команды | |

Не перенесено, потому что не относится к локальному инструменту: оболочка Tauri, Alembic, Postgres и Redis, аккаунты и биллинг, Celery, экспорт метрик и трассировки, Fernet для ключей, SBOM/SCA, веб-поиск, лендинг и блог. Сервер остаётся на `http.server`, зависимости — стандартная библиотека и PyYAML.

## Доказательства

Требование получает статус только из доказательств, и источник виден в отчёте:

- **тест модели**: `test_rN` запущен и прошёл;
- **атака Verify**: собственные входы (значение с `\n`, границы длины, кавычка) против кода;
- **правило по AST**: SQL из ввода, ввод в логах;
- **Анализатор Vishap**: если в spec есть `check: analyzer`.

Если доказательства нет, статус `needs_verification` или `not_verified`, не `passed`.

## Гейт

`--gate` блокирует запись (код выхода 1), если: ошибка сборки; critical/high требование не `passed`; Анализатор нашёл ошибку; покрытие меньше 80%; открыта critical-дыра; spec старше 90 дней; Verify не смог что-то запустить. `--force` пишет всё равно, в трассе `forced: true`.

## Границы доверия

1. Пользователь → сервер: loopback или токен, Host/Origin, JSON, 256 КБ, один прогон, лимит запросов на адрес.
2. Сервер → модель: текст spec уходит провайдеру после `tools/redact` (ключи и пароли заменены); данные между случайными маркерами.
3. Модель → Verify: код модели исполняется дочерним процессом **без изоляции** (см. SECURITY.md).
4. Deliver → диск: только внутри `--out`; атомарная запись; откат.

## Поток данных в API

`POST /api/generate` → `api/jobs.handle_generate` (или `POST /api/generate/async` → `start_job`, поток, опрос через `GET /api/jobs/<id>`) → `pipeline/orchestrator.run_pipeline` в пустой временной папке (`allow_write=False`) → `api/reports.report` → JSON с `files`, `diff`, `trace`, `log`. Сервер ничего не пишет на свой диск.
