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
| `pipeline/orchestrator.py` | `run_pipeline`: все этапы подряд и цикл исправлений |
| `pipeline/stages.py` | реестр этапов и их промптов |
| `pipeline/prompts.py` | загрузка промптов, `wrap_data()` |
| `prompts/*.md` | все промпты (см. `prompts/README.md`) |
| `llm/` | `providers.py` настройки из окружения, `client.py` один вызов чата, `_scrub.py` |
| `api/` | проверка Host/Origin и токена, лимит одного прогона, настройки модели из браузера, отчёт |
| `main.py` | HTTP-сервер: форма и API |
| `cli.py` | командная строка |
| `config.py`, `version.py` | пути, пределы, переключатели окружения; версия |
| `tools/sarif.py`, `tools/examples.py` | вывод SARIF 2.1.0; примеры для формы |
| `web/index.html` | форма: один файл, без сборки |

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

1. Пользователь → сервер: loopback или токен, Host/Origin, JSON, 256 КБ, один прогон.
2. Сервер → модель: текст spec уходит провайдеру; данные между случайными маркерами.
3. Модель → Verify: код модели исполняется дочерним процессом **без изоляции** (см. SECURITY.md).
4. Deliver → диск: только внутри `--out`; атомарная запись; откат.

## Поток данных в API

`POST /api/generate` → `api/jobs.handle_generate` → `pipeline/orchestrator.run_pipeline` в пустой временной папке (`allow_write=False`) → `api/reports.report` → JSON с `files`, `diff`, `trace`, `log`. Сервер ничего не пишет на свой диск.
