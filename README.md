# vishap-generator

Генератор кода из спецификации, который доказывает результат. На входе `spec.yaml`, на выходе файлы, тесты и трасса «требование → код → тест → находка». Каждое требование получает статус `passed`, `failed`, `needs_verification` или `not_verified`; «не доказано» не выдаётся за «прошло».

Живёт отдельно от Vishap. Анализатор Vishap подключается как внешняя программа (`vishap analyze`), не как зависимость.

Статус: готов к локальному использованию. Код: https://github.com/dvddv9/vishap-generator. Страница на Render: https://vishap-generator.onrender.com/ — проверка спецификации открыта всем (без модели и без запуска кода), генерация только с токеном владельца (`GENERATOR_PUBLIC_CHECK=1`, `deploy/README.md`; бесплатный тариф засыпает, первый запрос идёт около минуты).

## Пять этапов

1. **Intake**: `spec.yaml` → требования R1..Rn с приоритетом (critical / high / medium). Без LLM.
2. **Design**: план файлов и дыры в спецификации (`assumption`, `contradiction`, `missing_input`). Правила без LLM. Затем один вызов модели сверяет свободный `text` с требованиями: что в тексте сказано, но ни одно требование не покрывает, попадает в дыры как `assumption` (не блокирует гейт). Цитата обязана быть дословно из текста, выдуманные отбрасываются.
3. **Build**: модель пишет код и тесты (`test_rN` на каждое требование). Проверки до Verify: `ast.parse`, `ruff` если установлен.
4. **Verify**: три вывода: вердикт по коду, вердикт по спецификации (`stale`, если `updated` старше 90 дней), покрытие (меньше 80% не считается проходом). Доказательства трёх видов: тесты модели, собственные атаки Verify (в том числе `значение\n`, границы длины, кавычка), статические правила (SQL из ввода, ввод в логах). Анализатор Vishap запускается при `check: analyzer`. Если Verify нашёл проблему, до `--repairs` раундов (по умолчанию 2) модель получает её текст и исправляет файлы.
5. **Deliver**: гейт, diff, backup, запись, трасса `.vishap/<имя>.trace.json`, откат.

## Установка

    cd C:\AI\vishap-generator
    python -m pip install -e .

Без установки то же самое работает из папки проекта: `$env:PYTHONPATH = "src"; python -m generator generate ...`.

Нужен Python 3.11+ и PyYAML (ставится сам). Необязательно: `ruff` и `coverage` (`python -m pip install -e .[full]`). Без `coverage` покрытие считает встроенный построчный счётчик (в отчёте так и написано); без `ruff` линтер пропускается с пометкой, Flask (если сгенерированный код его использует), команда `vishap` (Анализатор).

## Модель

Любой OpenAI-совместимый endpoint. Настройки только из окружения, ключ никуда не пишется:

    $env:VISHAP_LLM_PROVIDER = "custom"
    $env:CUSTOM_LLM_URL      = "https://api.deepseek.com"
    $env:CUSTOM_LLM_MODEL    = "deepseek-flash"
    $env:CUSTOM_LLM_KEY      = "<ключ>"
    $env:CUSTOM_LLM_THINKING = "disabled"      # для DeepSeek: иначе рассуждения съедают лимит токенов

Задавайте на сессию PowerShell, не постоянными переменными Windows: Vishap читает `.env` без перезаписи, и постоянные `CUSTOM_LLM_*` перебили бы его настройки. Для локального сервера (Ollama) ключ не нужен, адрес `http://localhost:...`.

Анализатор: команда по умолчанию `vishap`, другую можно задать `VISHAP_ANALYZER_CMD` (например `python -m src.cli`). Анализатор отправляет читаемый код своей модели. Если команды нет, проверка `skipped` и это видно в отчёте.

## Командная строка

    vishap-generator init spec.yaml
    vishap-generator generate examples/spec-clean.yaml --out out/
    vishap-generator generate spec.yaml --out src/ --gate
    vishap-generator generate spec.yaml --out src/ --dry-run
    vishap-generator generate spec.yaml --no-llm
    vishap-generator rollback 8f3a1c2e --out src/
    vishap-generator batch specs/ --out out/ --workers 2
    vishap-generator baseline spec.yaml        # принять текущие critical-дыры осознанно
    vishap-generator history --out src/
    vishap-generator info                      # версия, модель, хэши промптов, проблемы настройки

(`python -m generator ...` работает так же.)

| флаг | что делает |
|---|---|
| `--out DIR` | куда писать файлы |
| `--gate` | блокирует запись (код выхода 1), если: провален или не доказан critical/high; покрытие меньше 80%; открыта critical-дыра; спецификация stale; ошибка сборки; Analyzer нашёл ошибку; Verify не смог что-то запустить |
| `--require-coverage` | с `--gate`: покрытие, которое не удалось посчитать (тесты не запустились), тоже блокирует; без флага оно только отмечено `skipped` |
| `--force` | только с `--gate`: записать всё равно; в трассе `forced: true` |
| `--dry-run` | показать diff, ничего не писать |
| `--no-llm` | только Intake и Design (проверка спецификации) |
| `--no-analyzer` | не запускать Анализатор |
| `--no-text-check` | не просить модель сверить свободный `text` с требованиями |
| `--repairs N` | раунды исправления (0 — без них; без флага решает `--effort`) |
| `--effort quick\|standard\|deep` | сколько работы: quick — 1 исправление, без сверки текста и Анализатора; standard — как раньше; deep — 3 исправления, 3 кандидата, `--cove`. Отдельный флаг сильнее имени |
| `--candidates N` | N ответов модели (1–5): каждый собирается и проверяется Verify, остаётся тот, у которого больше доказано; стоит N сборок |
| `--cove` | ещё один вызов модели: она отвечает только по spec, что сервис должен делать на странных значениях (`é`, арабская цифра, `_`, пробел); код запускается на тех же значениях, расхождения идут в заметки |
| `--strict` | отказать, если в spec нет больше половины ключевых данных, и назвать, чего нет (код выхода 2) |
| `--repro` | температура 0 и фиксированный seed; не вместе с несколькими кандидатами |
| `--json FILE`, `--sarif FILE`, `--report FILE` | полный результат / SARIF 2.1.0 / отчёт Markdown |

После прогона печатается строка `usage`: вызовы модели, токены, время и цена (цена только если заданы `GENERATOR_PRICE_IN` и `GENERATOR_PRICE_OUT`, USD за 1M токенов). Пороги гейта можно задать в `.vishap-generator.yml` (образец: `.vishap-generator.yml.example`).

Без `--gate` файлы пишутся всегда, провалы и дыры остаются в отчёте. Коды выхода: 0 готово, 1 гейт заблокировал, 2 ошибка (спецификация, модель, запись).

Откат: `rollback ID` возвращает старые файлы и удаляет созданные. Отказывается, если файл изменён после прогона (`--force` перебивает). Backup и манифест лежат в `<out>/.vishap/runs/<ID>/`.

### Что проверяется сверх Verify (0.6.0)

- **Таблица STRIDE** читает spec, не код: для каждой из шести угроз есть ли требование (`covered`, `partial`, `not_covered`, `not_applicable`). После Verify в строке появляется `proof`: доказаны ли эти требования. Блокирует только по ключу гейта `require_stride`.
- **Инструкции к модели в spec** («игнорируй предыдущие инструкции») — critical-дыра `injection`; три и больше останавливают прогон. **Секрет в spec** — critical-дыра `secret` (виды и число, не значения). Поле `domain:` (bank, medical, retail и другие) добавляет напоминания «подумали ли о ...», они не блокируют.
- **Память раундов**: модель при исправлении видит проблемы прошлых раундов; те же проблемы два раза подряд останавливают цикл.
- **Недодача**: если модель не прислала больше `max_loss_pct` (30) запланированных файлов кода и тестов, это проблема `incomplete`.
- Пороги в `.vishap-generator.yml`: `strict_missing_pct`, `require_stride`, `fail_on_cove`, `max_loss_pct`, `require_analyzer` (блокировать, если Анализатор не запускался), `min_mutation_score`.
- **Допустимый ввод, на который песочница не смогла ответить** (нет базы, нет сети), больше не «проходит»: проба получает статус `inconclusive` и попадает в «Notes» как не доказанная. Ошибка в коде на допустимом вводе (`TypeError`, `NameError` и подобные) проваливает требование.
- **Допущения модели** (`# assumption:` в коде) собираются в список в отчёте, трассе и на странице результата; среда (Python, библиотеки из плана) тоже: если Flask не установлен, модель узнаёт об этом до написания кода.
- **Мутационная проверка тестов** (`--mutants N`, по умолчанию 12, в deep 30, в quick нет; `GENERATOR_MUTANTS=0` выключает): код меняют по мелочи (`fullmatch` на `match`, `==` на `!=`, код статуса на единицу больше), тесты модели запускают на каждом изменении. Не замеченное тестами изменение попадает в отчёт со строкой и сутью. В deep модели один раз предлагают дописать тесты на такие изменения; новые файлы принимаются, только если всё проходит и оценка выросла. Ключ гейта `min_mutation_score`.
- **Вопросы автору**: каждая дыра spec превращается в вопрос, рядом стоит то, что модель решила сама (`# assumption:`). Ответ в spec даёт требование, тест и атаку вместо догадки. С `--candidates` отдельно показываются пробы, на которые кандидаты ответили по-разному.
- **Стоимость** показывается, только если заданы `GENERATOR_PRICE_IN` и `GENERATOR_PRICE_OUT`; иначе «not priced», а не $0.

## REST API и веб-форма

    vishap-generator serve            # http://127.0.0.1:8787/

- `GET /` — веб-форма в стиле Vishap (светлая и тёмная тема, телефон тоже). Страницы: главная (статус, как это работает, недавние прогоны, вопросы), «Generate» (spec с примерами и полями, опции прогона, настройки модели) и страница результата с вкладками Summary, Requirements, Files, Gaps, Analyzer, Diff, Audit, Full result. Если сборка нашла ошибки (например, тест называет несуществующее требование), вердикт будет `needs verification`, а в Summary появится карточка «Build check».
- Настройки модели в форме (URL, имя, ключ) живут в `sessionStorage` вкладки и уходят только в запрос; сервер их не хранит и не пишет в лог. Принимаются, когда сервер на loopback или задано `GENERATOR_ALLOW_CLIENT_LLM=1`; иначе используется модель из `CUSTOM_LLM_*` сервера.
- `GET /health`, `GET /api/status` (какая модель настроена, есть ли Analyzer и coverage, нужен ли токен), `GET /api/examples` (пять примеров спецификации, среди них с JSON-телом и со значением в пути).
- `POST /api/check` `{"spec": "<yaml>"}` — Intake и Design.
- `POST /api/generate` `{"spec": "<yaml>", "gate": false, "repairs": 2, "no_analyzer": false, "effort": "deep", "candidates": 3, "cove": true, "strict": false}` — все этапы (`effort`, `candidates`, `cove`, `strict` необязательны; неверное значение — 400, отказ `strict` — 422). Ничего не пишет на диск сервера: файлы, `diff`, `trace`, `log`, `markdown`, `stages` и `usage` приходят в ответе.
- `POST /api/generate/async` (то же тело) → `202 {"job": "<id>"}`; `GET /api/jobs/<id>?since=N` → статус, текущая стадия, новые строки лога, а когда готово, тот же ответ, что у `/api/generate`. Форма использует именно его. Задачи живут в памяти сервера час.
- `GET /api/providers` — провайдеры, которых может выбрать браузер (URL из запроса сервер не берёт).

Защита: по умолчанию только `127.0.0.1`; для другого адреса обязателен `GENERATOR_API_TOKEN` (заголовок `Authorization: Bearer ...`). Принимается только `application/json`, проверяются `Host` и `Origin` (страница с чужого сайта не может потратить ваш ключ модели), тело до 256 КБ, одновременно один прогон (второй получает 429), не больше `GENERATOR_RATE_LIMIT` запросов в минуту с одного адреса (по умолчанию 30, 0 — без лимита; ответ 429 с `Retry-After`). Журнал: `LOG_LEVEL`, `LOG_FORMAT=json`; в нём метод, путь, статус и id запроса, без тел.

## Спецификация

Два примера: `examples/spec-clean.yaml` (без открытых дыр, с него начинать) и `examples/spec.yaml` (нарочно без ответа 400/422: Design сообщает критическую дыру G1, `--gate` заблокирует запись). Известные поля проверяются при загрузке; незнакомое поле останавливает прогон и перечисляет известные.

## Безопасность и пределы

- **Verify не изолирует код.** Сгенерированный код запускается подпроцессом с правами пользователя (чистое окружение без ключей, таймаут, `-X utf8`). Это проверка работы кооперативной модели, не защита от враждебного кода. Перед работой с чужими спецификациями нужен Docker или похожая изоляция.
- Файлы пишутся только внутри `--out`: пути проверяются, абсолютные, `..` и симлинки отвергаются; сбой посреди записи отменяет прогон целиком.
- `material_hash` считается на сервере по байтам спецификации.
- Текст спецификации передаётся модели как данные между маркерами, не как инструкции. Перед этим из него вырезаются ключи, токены, приватные ключи, JWT и пароли (`tools/redact.py`). Это не гарантия: ловятся типичные формы секретов, не всё, что человек может напечатать.
- Свободный `text` читается только моделью при Build. Требования создаются только из структурных полей: факт, сказанный лишь в `text`, считается отсутствующим.
- Покрытие строчное, без веток. Атаки Verify идут без базы данных: ветки 200 и 404 доказаны тестами модели с подставной базой, на настоящей БД Verify не проверяет.
- Не поддерживается: цели кроме `python/*` проверяются только на уровне плана и `ast`, атаки Verify работают для `http-endpoint` с входами в `query`, `header`, `path` (в маршруте должен быть `<имя>`, `<тип:имя>` или `{имя}`) и `body` (один JSON-объект; поля вложенных объектов и массивы не атакуются).

## Тесты

    python -m unittest discover -s tests -t .

## Структура

Как у Vishap: код по папкам, промпты файлами, служебные файлы в корне.

    src/generator/
      version.py  config.py  cli.py  main.py        версия, настройки, командная строка, HTTP-сервер
      api/        auth errors rate_limit llm_config reports jobs job_store job_store_memory
      llm/        custom_client client _observe providers _scrub
      pipeline/   intake design build generate verify verdict deliver textcheck batch cost
                  orchestrator (все этапы)  stages (реестр, часы)  prompts (загрузка)
                  effort candidates cove (глубина, лучший из N, сверка с запуском)
                  sandbox + _sandbox_runner (дочерний процесс)
      tools/      spec gaps analyzer sarif examples static_scan quality_gate baseline
                  redact provenance report stride injection strict domains spec_text
      storage/    history
      observability/ logging
      prompts/    00_rules  02_design_textcheck  03_build  03_build_repair  04_verify_cove  (.md)
      web/        index.html
    tests/        по файлу на модуль, плюс test_prompts и test_structure
    docs/         ARCHITECTURE FAQ LIMITATIONS ROADMAP VISHAP HISTORY stages
    deploy/       systemd, заметки о развёртывании
    examples/     spec.yaml (с дырой), spec-clean.yaml
    scripts/      check_version.py, try_generate.py, try_verify.py

В корне: `AGENTS.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `LICENSE` (AGPL-3.0-or-later), `Dockerfile`, `docker-compose.yml`, `.env.example`, `ruff.toml`, `requirements*.txt`, `run_tests.py`, `run_local.ps1`, `start_generator.bat`, `.pre-commit-config.yaml`, `.github/`.

Промпты: `src/generator/prompts/README.md`. Пути импорта изменились в 0.4.0: `generator.pipeline.verify`, `generator.tools.spec`, `generator.pipeline.orchestrator.run_pipeline`, `generator.main.serve`.

Запуск без командной строки: `run_local.ps1` или `start_generator.bat` (откроют форму на http://127.0.0.1:8787/). Проверка перед коммитом: `python run_tests.py --lint`.
