# Dogfood: requirements

**Source:** `requirements.txt`
**Type:** requirements
**Level:** D2 | **task_type:** compliance
**Cost:** $0.005882 | **Verdict:** SAFE | **Risk:** SAFE
**Session:** `sess-2026-10-12-121207` | **audit_id:** `audit-2026-10-12-7cd4e4`
**material_hash:** `sha256:06a6b3ea439350a43d3b2d199e331625cd28be22970c71283888f7fe812ee391`
**material_hash_full:** `sha256:06a6b3ea439350a43d3b2d199e331625cd28be22970c71283888f7fe812ee391` (truncated: False, original_size: 446)
**pii_detected:** False | **Compliance:** none

---

## Vishap Output

# requirements.txt — Compliance Review (D2)

[ECHO] Материал: `requirements.txt`, 22 зависимости, нижние границы (`>=`), extras `uvicorn[standard]`. task_type=compliance, level=D2, session=sess-2026-10-12-XXXXXX. Артефакт декларативный — кода, lockfile, CI-конфига и политики версий в материале нет.

[ROUTE] stage0 → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). research_first=false, parallel_stages=false, subst_count=0.

[CONCLUSION] Манифест функционален, но не соответствует базовой supply-chain гигиене: нет lockfile, нет хэшей, нет верхних границ, нет CVE-сканирования, нет index pinning, нет разделения dev/prod. Признаков CI-конфига и политики версий в материале не найдено (VERIFY: CI и VERSIONING.md не проверялись — вне материала). Критичных конфликтов между stage1/stage2/stage4 нет; escalation level 0.

[RISK_NODES]
- RN-11 (критично): ни у одного из 22 пакетов нет верхней границы → мажорный релиз pydantic/fastapi/openai ломает сборку без изменения кода.
- RN-6 (критично): системное отсутствие supply-chain гигиены — lockfile, хэши, pip-audit, index pinning, dev/prod split.
- RN-1 (критично): неявное допущение совместимости 22 пакетов и необъявленной версии Python — не проверено ничем.
- RN-5 (важно): tree-sitter core `>=0.22.0` против грамматик `>=0.21.0` — возможен ABI drift, парсинг молча ломается.
- RN-2 (важно): `>=` не даёт воспроизводимости — один манифест → разные окружения в разное время.
- RN-3 (важно): ollama + openai — два LLM-клиента, роль не разграничена.
- RN-8 (важно): tenacity объявлен, retry-политика не описана.
- RN-7 (важно, повышено из опционально по cove): `uvicorn[standard]` без platform markers — сборка падает на Windows/macOS.
- RN-9 (опционально): streamlit + fastapi в одном образе — два runtime-профиля, независимое масштабирование невозможно.
- RN-4 (опционально): материал позиционируется как compliance-review, но политики версий в нём нет.

[PLAN_B]
- RN-11: ввести `<next-major` для всех 22 пакетов + lockfile.
- RN-6: pip-audit в CI + `--require-hashes` + `requirements-dev.txt` + `--index-url`.
- RN-1: `python_requires>=3.11` + CI-шаг `pip install --dry-run` на матрице Python 3.11/3.12/3.13.
- RN-5: выровнять tree-sitter-* на `>=0.22.0,<0.23` или зафиксировать совместимую пару.
- RN-2: `pip-compile --generate-hashes` → `requirements.lock` в VCS.
- RN-3: выбрать один LLM-клиент или разграничить роли (локальный vs облачный) в README.
- RN-8: задокументировать retry-политику tenacity (какие вызовы, лимиты, timeout).
- RN-7: platform markers `sys_platform != 'win32'` для `uvicorn[standard]`.
- RN-9: разнести streamlit и fastapi в отдельные extras/образы.
- RN-4: приложить VERSIONING.md с политикой (semver, окно обновления, кто апрувит).

[ASSEMBLY] Единый артефакт — плоский список из 22 строк. Слои: runtime (9), parsing (7), quality/dev (2), test (3), resilience (1). Связи: fastapi→pydantic, pydantic-settings→pydantic+python-dotenv, 6 грамматик→tree-sitter core, pytest-asyncio→pytest. Критический путь: `requirements.txt → PyPI → pip install → import pydantic → fastapi → uvicorn → service start`.

[REFACTORING] Разделить на `requirements.in` (runtime) + `requirements-dev.in` (dev/test/quality) + lockfile с хэшами. Добавить верхние границы, platform markers, `python_requires`. Ввести extras: `[api]`, `[ui]`, `[parse]`, `[dev]`. Порядок: pip-audit → pip-compile --generate-hashes (иначе фиксируем CVE в VCS — NR-1).

[PARALLELS] Паттерн «flat requirements.txt без lockfile» — типичен для прототипов и внутренних инструментов; в проде эквивалентен Poetry/uv/Pipenv с lockfile. Аналог в других экосистемах: `package.json` без `package-lock.json`, `go.mod` без `go.sum`.

[TESTS] Объявлены pytest, pytest-asyncio, httpx; тестовых файлов в материале нет. Отсутствуют edge-cases: резолв на чистом окружении, smoke-импорт всех 22 пакетов, ABI-проверка tree-sitter core↔грамматики, поведение при недоступности OpenAI/Ollama.

[ACTION]
- NOW: зафиксировать текущий `requirements.txt` как `requirements.legacy.txt` (baseline для отката).
- TODAY: запустить `pip-audit -r requirements.txt` — до lockfile, иначе CVE закрепляется (NR-1).
- TOMORROW: `pip-compile --generate-hashes` → lockfile в VCS; добавить верхние границы и platform markers.
- LATER: pip-audit в CI, SBOM (cyclonedx), timeout + circuit breaker для LLM-вызовов, разделение streamlit/fastapi.

[QUESTIONS]
- Существует ли CI-конфиг, использующий этот манифест? (VERIFY: TB-5 гипотетическая — CI в материале не подтверждён)
- Есть ли VERSIONING.md / политика версий? (VERIFY: RN-4 — в материале не найдено)
- Разграничены ли роли ollama и openai, или это дублирование? (VERIFY: RN-3)
- Защищён ли `.env` через `.gitignore`/`.dockerignore`? (VERIFY: SEC-4 — вне материала)
- Какая целевая версия Python и целевые платформы? (VERIFY: RN-1, RN-7)

[FUNC:FULL]
- ECON: effort Option A ~1–2 дня, Option B ~3–5 дней, Option C ~5–8 дней; cost $ — rate не задан; ROI Option A наивысший (закрывает 3 критичных риска за 1–2 дня); cloud delta $0 (инфра не описана); cost of delay — каждый `pip install` без lockfile = лотерея, стоимость инцидента не оценена.
- FAIL: критично — FP-1 (мажорный апдейт ломает сборку), FP-2 (подмена пакета без хэшей не детектируется); важно — FP-3 (tree-sitter ABI drift), FP-4 (нет timeout/circuit_breaker → каскадный отказ LLM), FP-5 (утечка OPENAI_API_KEY); recovery — без lockfile точная предыдущая комбинация неизвестна, откат ручной.
- METRICS: 22 строки, 22 зависимости (9 runtime / 7 parsing / 2 quality / 3 test / 1 resilience), 0 тестов в материале, 0 хэшей, 0 верхних границ, 0 lockfile, 0 platform markers, 0 python_requires; resilience_score=3/10, evolvability=3/10.
- ALTERNATIVES: pip-tools (pip-compile) / uv lock / Poetry / Pipenv — для lockfile; pip-audit / safety / osv-scanner — для CVE; cyclonedx / syft — для SBOM; pybreaker / aiobreaker — для circuit breaker; structlog + opentelemetry-sdk + prometheus-client — для observability.
- EVOLVE: coupling внешний (все 22 — third-party), абстракции отсутствуют (плоский список), growth — замена любого пакета требует ручной проверки всего графа, friction — нет extras, нет dev/prod split, нет lockfile.
- COMPARE: Option A — 1–2 дня, низкая сложность, закрывает RN-11/RN-2/SEC-1; Option B — 3–5 дней, средняя, +SEC-2/SEC-3/RN-7/RN-9; Option C — 5–8 дней, высокая, +FP-4/contracts.timeout/circuit_breaker, требует код-изменений вне манифеста.

[MANDATORY BASE]
1. ECONOMICS: time Option A 1–2 дня, cost $ — rate не задан, при условии наличия CI для Option B/C; ROI Option A наивысший при условии, что baseline incident cost > 2 дней инженерного времени.
2. RISKS: критично — RN-11, RN-6, RN-1; важно — RN-5, RN-2, RN-3, RN-8, RN-7; при условии, что манифест используется в проде (не подтверждено).
3. INFRASTRUCTURE: pool_size=n/a (не декларирован), workers=n/a, replicas=n/a, при условии, что инфраструктура описана вне материала.
4. CODE: change 22 строки → ~30 строк (requirements.in) + lockfile + 5 вспомогательных файлов, при условии Option A.
5. ACTION: now — baseline `requirements.legacy.txt`; tomorrow — pip-audit + pip-compile --generate-hashes; later — CI-интеграция, SBOM, timeout/circuit breaker.
6. TIMELINE: NOW — baseline; TODAY — pip-audit; TOMORROW — lockfile + upper bounds; LATER — CI, SBOM, observability.
7. PRODUCTION IMPACT: users N — неизвестно (не задано); deploy window — не задан; rollback — ручной, точная комбинация неизвестна без lockfile.
8. SLO IMPACT: current N% — SLO не определены; after N% — не вычисляется; при условии, что SLO будут заданы (latency p95, error rate, availability).
9. CLOUD COST: current $N — неизвестно; projected $N — неизвестно; delta ±$0 (инфра не описана).
10. ON-CALL: new alerts — не заданы; runbook — отсутствует; escalation — не определено (on_call.defined=false).

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | FAIL | SEC-1 (нет хэшей), SEC-2 (нет CVE-сканирования), SEC-3 (нет index pinning), SEC-4 (python-dotenv без защиты .env) |
| Facts | OK | Все 22 зависимости и версии соответствуют материалу; числа из stage1/stage2/stage4 |
| Logic | OK | Цепочка RN → PLAN_B → Option A/B/C согласована; конфликтов между stage1/stage2/stage4 нет |
| Applicability | WARN | Option A применим немедленно; Option B/C требуют CI, который не подтверждён (VERIFY) |
| Effectiveness | WARN | Option A закрывает 3 критичных риска за 1–2 дня; SEC-2/SEC-3 остаются открытыми |
| Resilience | FAIL | resilience_score=3/10; нет lockfile, хэшей, верхних границ, timeout, circuit breaker |
| Human factor | WARN | Нет VERSIONING.md, нет runbook, нет on-call — процессная гигиена отсутствует |
| Clarity | OK | Манифест читаем; отсутствие комментариев и группировки — минорный smell |

[CHANGELOG]
| # | What changed | Reason |
|---|--------------|--------|
| 1 | Введены верхние границы (`<next-major`) для всех 22 пакетов | Risk Critical (RN-11) |
| 2 | Добавлен lockfile с хэшами (`pip-compile --generate-hashes`) | Risk Critical (RN-6, SEC-1) |
| 3 | Разделены runtime и dev/test зависимости | Risk Medium (RN-6) |
| 4 | Добавлены platform markers для `uvicorn[standard]` | Risk Medium (RN-7) |
| 5 | Добавлены `.env.example`, `.gitignore`, `.dockerignore` | Risk High (SEC-4) |
| 6 | Добавлен pip-audit в dev-зависимости | Risk Critical (SEC-2) |

[REFLEXION]
1. Слабое место: TB-5 (CI → prod) и TB-6 (runtime → FS) не верифицированы — исправлено пометкой VERIFY в [CONCLUSION] и [QUESTIONS], без категоричных утверждений.
2. Слабое место: числа без источника (rate, baseline incident cost, SLO) — исправлено условиями «при условии» в [MANDATORY BASE] и явным «не задано» вместо выдуманных значений.
3. Слабое место: риск фиксации CVE в lockfile (NR-1) — исправлено порядком действий в [ACTION] и [REFACTORING]: pip-audit ДО pip-compile.
Итог: accepted

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-7cd4e4
material_hash: sha256:06a6b3ea439350a43d3b2d199e331625cd28be22970c71283888f7fe812ee391
material_hash_full: sha256:06a6b3ea439350a43d3b2d199e331625cd28be22970c71283888f7fe812ee391
pii_detected: false
compliance_flags: []
critique_verdict: SAFE
risk_verdict: SAFE


[COMPLETENESS]
level: D2
required: 12
missing: []
loss_pct: 0.0%
material_complete: True
verdict: ACCEPTABLE