# Стадии

Порядок прогона: Intake → Design (files + gaps) → Build → Verify → Deliver.

Intake: без LLM. Требования из inputs, outputs, must_never, should, may. Priority: must_never = critical; inputs, outputs, should = high; may = medium.

Design: выходы — files (с requirements, measures, library_check) и gaps (assumption — noted; contradiction, missing_input — critical).

Build: test_rN на каждое требование; ast.parse и ruff обязательны до Verify.

Verify: вердикт по коду, вердикт по спецификации, coverage (порог 80%).

Deliver: трасса, diff, backup, rollback. Запись только в output-папку и только по правилам гейта.

Открыто: проверка библиотек по документации (`library_check` только называет библиотеки), чтение свободного `text` против требований, цели кроме `python/*`, изоляция запуска (Docker).
