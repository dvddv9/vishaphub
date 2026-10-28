# Dogfood: ci-tests

**Source:** `.github/workflows/tests.yml`
**Type:** ci-tests
**Level:** D2 | **task_type:** compliance
**Cost:** $0.005335 | **Verdict:** SAFE | **Risk:** SAFE
**Session:** `sess-2026-10-12-121050` | **audit_id:** `audit-2026-10-12-dbd2ad`
**material_hash:** `sha256:e41c537fe04087db2f001895a6a597eb7b233e97139e7008392e49787b2e071f`
**material_hash_full:** `sha256:e41c537fe04087db2f001895a6a597eb7b233e97139e7008392e49787b2e071f` (truncated: False, original_size: 805)
**pii_detected:** False | **Compliance:** none

---

## Vishap Output

# CI Workflow Review — `.github/workflows/tests.yml`

[ECHO] GitHub Actions workflow `tests`: триггеры push/PR на `main`, один job `test` на `ubuntu-latest`, матрица Python `[3.11, 3.12]`, шаги checkout@v4 → setup-python@v5 → `pip install -e .[dev]` → `python run_tests.py` → `ast.parse(src/**/*.py)`. ~40 строк, декларативный YAML.

[ROUTE] stage0 (compliance, D2) → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). Sequential, без параллельных стадий, `research_first: false`.

[CONCLUSION] Workflow функционален и покрывает unit+mock на двух версиях Python, но имеет 4 «важно»-долга: отсутствие `permissions:` (SEC-1), пиннинг actions по тегу вместо SHA (SEC-2), отсутствие `timeout-minutes` (RN-8), отсутствие `concurrency`-группы (RN-6/RN-10). Критичных узлов не выявлено. Существование `run_tests.py`, `src/` и состава `[dev]` не подтверждено (VERIFY: не проверено — нет доступа к репо).

[RISK_NODES]
- **RN-1 (важно)** — неявное допущение: наличие `run_tests.py` и `src/`; при отсутствии job падает без явной диагностики.
- **RN-2 (важно)** — только `ubuntu-latest`, нет OS-матрицы и min-supported Python.
- **RN-4 (важно)** — заявлено «unit + mock», но нет coverage/lint/type-check гейтов.
- **RN-6 / RN-10 (важно)** — нет `concurrency: group` — параллельные push на main не сериализуются.
- **RN-8 (важно)** — нет `timeout-minutes` — зависший тест держит раннер до 360 мин.
- **RN-11 (важно)** — actions pinned by major tag (`@v4`/`@v5`), не SHA.
- **RN-3, RN-5, RN-7, RN-9 (опционально)** — дублирующий ast-шаг, unpinned pip, нет кэша, нет sharding.

[THREAT_MODEL]
- Компоненты: runner, checkout@v4, setup-python@v5, pip/PyPI, `run_tests.py`, `src/`, `GITHUB_TOKEN`.
- Trust boundaries: event→workflow, workflow→external actions, workflow→PyPI, workflow→repo code, workflow→token scope.
- Threats: **T** (подмена тега action), **T** (dependency confusion в `[dev]`), **E** (дефолтный write-scope токена), **I** (утечка env в логах тестов), **D** (зависший тест), **R** (противоречивые статусы при параллельных прогонах).
- Итог: 6 угроз — 0 критичных, 4 важных, 2 опциональных.

[SILENCE_LAYERS]
- **Input silence**: содержимое `run_tests.py`, состав `[dev]`, наличие `src/` — вне материала.
- **Assumption silence**: предполагается, что `run_tests.py` самодостаточен и покрывает unit+mock; что `[dev]` содержит нужные зависимости; что `src/` существует.
- **Consequence silence**: ложное «зелёное» из-за отсутствия coverage/lint/type-check и OS-матрицы; регрессии могут попасть в main до обнаружения.

[INTERSECTION_RISKS]
- matrix × fail-fast=true → падение одной ячейки отменяет вторую, скрытая несовместимость версий.
- pull_request × отсутствие permissions → внешний PR с дефолтным write-токеном.
- `pip install -e .[dev]` × отсутствие кэша → каждый прогон пересобирает пакет, рост времени CI.
- ast.parse × run_tests.py → двойная валидация синтаксиса, расхождение поведения.

[ASSEMBLY] Триггеры → job → matrix (2 ячейки) → checkout → setup-python → pip install → run_tests → syntax-check. Критический путь: `trigger → checkout → setup-python → pip-install → run_tests → syntax-check`. Циклов нет. `GITHUB_TOKEN` и repo-files — неявные зависимости.

[REFACTORING] Option A (обязательно, 0.5–1 день): `permissions: contents: read`, `timeout-minutes: 15`, `concurrency`-группа, `cache: 'pip'`, `fail-fast: false`, SHA-пиннинг actions, assert на `src/` и `run_tests.py`. Option B (опционально, 1.5–2.5 дня): coverage-gate, ruff+mypy, pip-audit, удаление дублирующего ast-шага. Option C (опционально, 3–4 дня): OS-матрица, sharding.

[PARALLELS] Аналогия: CI без `permissions`/`timeout`/`concurrency` — как прод-сервис без firewall, health-check и rate-limit. Работает, пока не столкнётся с реальной нагрузкой или атакой.

[TESTS]
- Присутствуют: unit, mock.
- Отсутствуют: integration, e2e, lint, type-check, coverage-gate, security-scan (pip-audit/bandit).
- Edge cases: отсутствие `src/` → ast-шаг падает; отсутствие `run_tests.py` → job падает; пустой `[dev]` → тесты не стартуют; 3.12-only синтаксис → падение на 3.11.

[ACTION]
- **NOW**: ничего не останавливать — workflow не деплоит, прод не затронут.
- **TODAY**: PR `chore/ci-hardening` с Option A (permissions, timeout, concurrency, cache, fail-fast: false, SHA-пиннинг, assert).
- **TOMORROW**: прогон на feature-ветке, проверка обеих ячеек матрицы, merge в main.
- **LATER**: Option B (coverage/lint/type-check) отдельным PR; Option C (OS-матрица) — при появлении платформенных регрессий.

[QUESTIONS]
- Существуют ли `run_tests.py` и `src/` в репо? (VERIFY: не проверено)
- Что входит в `[dev]` extras — есть ли там ruff/mypy/pytest-cov? (VERIFY: не проверено)
- Настроена ли branch protection с required checks на main? (VERIFY: не проверено)
- Есть ли владелец/эскалация для падений CI на main? (VERIFY: не проверено)

[FUNC:FULL]
- **ECON**: effort Option A ~0.5–1 день, Option B ~1.5–2.5 дня, Option C ~3–4 дня; cost $ — rate не задан; ROI Option A высокий (закрывает 4 «важно» риска); cloud delta 0 (A) / +30–50% времени (B) / +100% (C); cost of delay — экспозиция supply-chain и DoS-риска ежедневно.
- **FAIL**: критично — нет (0 критичных); важно — SEC-1 (permissions), SEC-2 (SHA-пиннинг), RN-8 (timeout), RN-6/RN-10 (concurrency); cascade — падение одной ячейки отменяет вторую (fail-fast=true); recovery — `git revert` коммита workflow, влияния на прод нет.
- **METRICS**: codebase ~40 строк YAML; deps 2 actions + pip + `[dev]`; tests unit+mock (coverage неизвестно); perf — нет кэша pip, нет timeout; quality — нет lint/type-check/coverage; infra — ubuntu-latest, 2 vCPU, 7 GB, 2 ячейки матрицы.
- **ALTERNATIVES**: Option A (hardening in place) / Option B (A + quality gates) / Option C (B + OS-матрица + sharding); альтернативы actions — SHA-пиннинг + Dependabot; альтернатива ast-шагу — ruff/mypy.
- **EVOLVE**: coupling 6/10 (неявная связь с `run_tests.py`/`src/`); abstractions 5/10 (нет reusable workflow/composite action); feature_add 7/10; module_replace 8/10; overall 6/10.
- **COMPARE**: Option A — 0.5–1 день, низкий риск, низкая сложность; Option B — 1.5–2.5 дня, средний риск, средняя сложность; Option C — 3–4 дня, средний риск, высокая сложность.

[MANDATORY BASE]
1. **ECONOMICS**: time Option A 0.5–1 день, cost $ — rate не задан, при условии GitHub-hosted runner и private repo.
2. **RISKS**: критично — нет; важно — SEC-1, SEC-2, RN-8, RN-6/RN-10, при условии дефолтного token scope и tag-пиннинга.
3. **INFRASTRUCTURE**: pool_size = n/a (GitHub-hosted), replicas = 2 (matrix), timeout_minutes = 15 (целевое), при условии ubuntu-latest standard.
4. **CODE**: change ~15–25 строк YAML (Option A), при условии одного файла `.github/workflows/tests.yml`.
5. **ACTION**: now — ничего не останавливать; tomorrow — PR Option A; later — Option B/C.
6. **TIMELINE**: NOW — мониторинг; TODAY — PR `chore/ci-hardening`; TOMORROW — merge в main; LATER — Option B/C.
7. **PRODUCTION IMPACT**: users 0 (workflow не деплоит), deploy window n/a, rollback ~1 min (git revert), при условии отсутствия deploy-шагов.
8. **SLO IMPACT**: current n/a (SLO не заданы), after n/a, при условии отсутствия SLO-определений для CI.
9. **CLOUD COST**: current $ — rate не задан, projected $ — rate не задан, delta ±$ — не вычислено, при условии private repo и биллинга по минутам.
10. **ON-CALL**: new alerts — нет (уведомления не настроены), runbook — отсутствует, escalation — не определена, при условии отсутствия CODEOWNERS.

[PLAN_B]
- SEC-1: `permissions: contents: read` на уровне workflow.
- SEC-2: пиннинг actions по полному commit SHA + Dependabot.
- SEC-3: фиксировать версию pip через `requirements-ci.txt` с хешами.
- SEC-4: ограничить permissions для `pull_request` контекста.
- RN-1: assert-шаг `test -f run_tests.py && test -d src`.
- RN-2: OS-матрица (ubuntu+macos) + min-supported Python.
- RN-3: убрать дублирующий ast-шаг или заменить на ruff/mypy.
- RN-4: coverage-gate (`--cov-fail-under=80`) + lint/type-check.
- RN-6/RN-10: `concurrency: {group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true}`.
- RN-7: `cache: 'pip'` в setup-python.
- RN-8: `timeout-minutes: 15` на job.
- RN-9: sharding тестов при росте времени прогона.
- RN-11: SHA-пиннинг actions.
- FP-1: retry на `pip install`.
- FP-3: assert на существование `src/`.
- FP-4: `fail-fast: false` в strategy.

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | WARN | SEC-1 (нет permissions), SEC-2 (tag-пиннинг), SEC-3 (unpinned pip) |
| Facts | WARN | Существование `run_tests.py`/`src/`/`[dev]` не подтверждено (VERIFY) |
| Logic | OK | Структура workflow консистентна, циклов нет |
| Applicability | OK | Option A применим за 0.5–1 день, низкий риск |
| Effectiveness | WARN | Нет coverage/lint/type-check — гарантия ниже заявленной (RN-4) |
| Resilience | WARN | Нет timeout, retry, concurrency-группы (RN-6/RN-8/RN-10) |
| Human factor | WARN | Нет CODEOWNERS, on-call, уведомлений при падении на main |
| Clarity | OK | Step names присутствуют, YAML schema-conformant |

[CHANGELOG]
| # | What changed | Reason |
|---|--------------|--------|
| 1 | Добавлен `permissions: contents: read` | Risk High (SEC-1) |
| 2 | Добавлен `timeout-minutes: 15` | Risk High (RN-8) |
| 3 | Добавлена `concurrency`-группа | Risk High (RN-6/RN-10) |
| 4 | Добавлен `cache: 'pip'` | Risk Medium (RN-7) |
| 5 | Добавлен `fail-fast: false` | Risk Medium (FP-4) |
| 6 | Добавлен assert-шаг на `src/` и `run_tests.py` | Risk Medium (RN-1/FP-3) |

[REFLEXION]
1. Слабое место: числа (effort, cost) без источника → исправлено: все числа помечены «rate не задан» или «при условии Z» в [MANDATORY BASE].
2. Слабое место: возможная категоричность про отсутствие `run_tests.py`/`src/` → исправлено: везде «не подтверждено (VERIFY: не проверено)».
3. Слабое место: риск дублирования

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-dbd2ad
material_hash: sha256:e41c537fe04087db2f001895a6a597eb7b233e97139e7008392e49787b2e071f
material_hash_full: sha256:e41c537fe04087db2f001895a6a597eb7b233e97139e7008392e49787b2e071f
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