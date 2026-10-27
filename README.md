# vishap-generator

Генератор кода из спецификации, который доказывает результат. Пишется отдельно от Vishap: Анализатор подключается как внешняя зависимость.

Статус: черновик, локально, без remote. Ничего не запускалось на реальном LLM.

## Этапы

1. **Intake** — spec.yaml → требования R1..Rn с priority (critical / high / medium). Без LLM.
2. **Design** — выход из двух частей: файлы (path, interface, requirements, measures, library_check) и дыры (gaps: assumption / contradiction / missing_input).
3. **Build** — код и тесты (test_rN), проверка ast.parse и ruff до Verify.
4. **Verify** — три выхода: вердикт по коду, вердикт по спецификации (stale: true старше 90 дней), coverage (< 80% → needs_verification).
5. **Deliver** — трасса (требование → код → тест → находка), diff, backup, rollback. Файлы пишутся только внутри output-папки.

## Гейт

- Без `--gate`: файлы пишутся, дыры и провалы — в отчёте.
- С `--gate`: блок записи при провале critical/high, coverage < 80%, открытой critical-дыре (contradiction / missing_input) или stale: true. Exit 1.
- `--force` с `--gate`: запись есть, отчёт помечен `forced: true`.

## Структура

    src/generator/intake.py
    src/generator/design.py
    src/generator/gaps.py
    src/generator/build.py
    src/generator/verify.py
    src/generator/deliver.py
    examples/spec.yaml
    tests/
    docs/stages.md
