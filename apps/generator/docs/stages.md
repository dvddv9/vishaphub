# Стадии

Порядок прогона: Intake → Design (files + gaps) → Build → Verify → Deliver.

Intake: без LLM. Требования из inputs, outputs, must_never, should, may. Priority: must_never = critical; inputs, outputs, should = high; may = medium.

Design: выходы — files (с requirements, measures, library_check) и gaps (assumption — noted; contradiction, missing_input — critical).

Build: test_rN на каждое требование; ast.parse и ruff обязательны до Verify.

Verify: вердикт по коду, вердикт по спецификации, coverage (порог 80%).

Deliver: трасса, diff, backup, rollback. Запись только в output-папку и только по правилам гейта.

Открыто: проверка библиотек по документации (`library_check` только называет библиотеки), чтение свободного `text` против требований, цели кроме `python/*`, изоляция запуска (Docker).

Учёт: каждая стадия записывается часами (`StageClock`): время, число прогонов, вызовы модели, токены. Repair-раунд — это снова Build. В трассе времени нет (трасса детерминирована), оно в `stages` результата и в отчёте.

Глубина (0.6.0): `--effort` задаёт число исправлений, кандидатов, сверку текста, Анализатор и COVE вместе. Design добавляет таблицу STRIDE (по spec) и дыры `injection`, `secret`, `reminder`. Build при `--candidates N` делает N ответов, каждый проходит Verify, остаётся лучший. После Verify при `--cove` идёт сверка с запуском кода на странных значениях. Раунды исправления помнят прошлые проблемы и останавливаются, если проблемы повторились.
