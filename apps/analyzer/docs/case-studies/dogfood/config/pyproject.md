# Dogfood: pyproject

**Source:** `pyproject.toml`
**Type:** pyproject
**Level:** D2 | **task_type:** compliance
**Cost:** $0.005529 | **Verdict:** REQUIRES_REVIEW | **Risk:** SAFE
**Session:** `sess-2026-10-12-121331` | **audit_id:** `audit-2026-10-12-cd109b`
**material_hash:** `sha256:f8b9404602686b74b74495d4ba3db085619015d2988ab18bcb2270699b279808`
**material_hash_full:** `sha256:f8b9404602686b74b74495d4ba3db085619015d2988ab18bcb2270699b279808` (truncated: False, original_size: 1150)
**pii_detected:** True | **Compliance:** EU AI Act, GDPR, 152-ФЗ

---

## Vishap Output

# CONVEYOR 5.7.0 — COMPLIANCE REVIEW: pyproject.toml

[ECHO] Материал: `pyproject.toml` (PEP 621/517/518 манифест, ~50 строк). task_type=compliance, level=D2, session=sess-2026-10-12-XXXXXX. Route: stage4→stage3. Substitutions: 0.

[ROUTE] stage0 (config/compliance) → stage1 (scanner) → stage2 (analyst, 11 RN + 5 SEC) → stage4 (synthesizer, 3 options) → stage5 (transmitter). Research_first=false, parallel=false.

[CONCLUSION] Манифест синтаксически валиден по PEP 621/517/440, но не соответствует практикам воспроизводимой и безопасной сборки: нет lockfile, нет верхних границ зависимостей, PII в METADATA, не-SPDX лицензия, отсутствует security-сканирование. Критичных блокеров публикации не найдено при условии приватного индекса; при публикации в публичный индекс — SEC-1 (PII) и RN-5 (license) становятся блокирующими. Признаков lockfile в материале не найдено (VERIFY: репозиторий не проверялся). Признаков CI-конфига не найдено (VERIFY: не проверялось).

[RISK_NODES]
- RN-1 (важно): `include=['src*']` — layout не верифицируем из манифеста; риск пустого wheel.
- RN-2 (важно): все deps `>=` без верхних границ → мажорный апдейт ломает рантайм.
- RN-3 (важно): streamlit + fastapi + uvicorn в одном runtime — двойной UI/ASGI-стек.
- RN-4 (опционально): description «6-stage» vs version 5.7.0 — косметика.
- RN-5 (важно): `license={text='Private'}` — не SPDX; SBOM/сканеры не распознают.
- RN-6 (важно): нет lockfile/CI/security-сканирования — незакрытый процесс.
- RN-7 (опционально): radon в runtime — лишний вес и поверхность.
- RN-8 (важно): сборка невоспроизводима без lockfile.
- RN-9 (опционально): `uvicorn[standard]` — платформенные бинарники (uvloop/httptools).
- RN-10 (опционально): потенциальный конфликт event loop fastapi+streamlit.
- RN-11 (важно→критично при отсутствии lockfile): ломающие изменения без pinning.

[PLAN_B]
- RN-1: assert wheel содержит `conveyor` в CI; явный `[tool.setuptools.packages.find]`.
- RN-2: uv.lock + dependabot с обязательным review.
- RN-3: extras-split `[ui]`/`[api]`/`[llm]`.
- RN-4: синхронизировать description с версией.
- RN-5: SPDX-выражение или `license-files`.
- RN-6: CI workflow (build + pip-audit + pytest + publish с attestation).
- RN-7: перенести radon в `[project.optional-dependencies].dev`.
- RN-8: hash-pinning в lockfile.
- RN-9: `uvicorn` + явные extras по платформе.
- RN-10: разнести streamlit и fastapi в отдельные entrypoints.
- RN-11: pinning мажорных версий (pydantic<3, openai<2, fastapi<1).
- SEC-1: убрать персональный email из authors.
- SEC-2: pip-audit в CI + dependabot.
- SEC-3: hash-pinning в lockfile.
- SEC-4: radon → dev.
- SEC-5: явный package-data whitelist.

[THREAT_MODEL] 7 угроз (0 critical, 6 important, 1 optional). Trust boundaries: developer→VCS, VCS→CI, CI→PyPI, runtime→LLM APIs, runtime→filesystem. Top-3: (1) T — unpinned deps → supply-chain tampering; (2) I — PII в METADATA; (3) D — отсутствие timeout/retry/circuit breaker на LLM-вызовах. Trust boundary runtime→ollama daemon (localhost) не отражена в stage2 (VERIFY).

[SILENCE_LAYERS]
- Input: нет данных о нагрузке/RPS/размере промптов.
- Assumption: предполагается src/ layout (не верифицируемо).
- Consequence: невоспроизводимая сборка + supply-chain exposure; откат не гарантирован при опубликованном wheel.

[INTERSECTION_RISKS]
- build-system × runtime deps: PEP 517 изоляция × unpinned → невоспроизводимость.
- runtime deps × security: python-dotenv × нет package-data whitelist → риск утечки .env в wheel.
- metadata × compliance: `license={text}` × SBOM/SPDX → блок публикации или «unknown».
- runtime deps × ops: fastapi+uvicorn+streamlit × нет CI/observability → инциденты не диагностируются.

[ASSEMBLY] Единый манифест, 6 слоёв (build-system, project, optional-deps, scripts, packages.find, tool configs). Cohesion high, coupling внешний (12 runtime + 3 dev + 2 build). Точка невозврата: `build-backend = setuptools.build_meta`.

[REFACTORING] Вариант A (minimal hardening): pin + lock + SPDX + PII scrub + radon→dev + package-data. Diff минимальный, обратимо, закрывает SEC-1/2/3/4/5 и RN-2/5/7/11. Вариант B (extras-split + CI): + RN-3/6. Вариант C (full split): только при подтверждении RN-10.

[PARALLELS] Аналогия: манифест без lockfile ≈ Dockerfile с `:latest` — работает сегодня, ломается завтра без изменения файла. PII в METADATA ≈ email в git-коммите — после публикации не отозвать.

[TESTS] pytest>=8.0.0 + pytest-asyncio>=0.23.0, testpaths=['tests']. Coverage-инструмент не указан (нет pytest-cov). Содержимое tests/ не в материале (VERIFY). Edge cases не видны.

[ACTION]
- NOW: убрать персональный email из `authors` (SEC-1) — до любой публикации.
- TODAY: заменить `license={text='Private'}` на SPDX (RN-5); перенести radon в dev (RN-7); добавить верхние границы для pydantic/openai/fastapi (RN-11).
- TOMORROW: сгенерировать uv.lock (RN-8); добавить package-data whitelist (SEC-5); проверить wheel contents (RN-1).
- LATER: CI workflow + pip-audit + dependabot (RN-6, SEC-2); extras-split (RN-3).

[QUESTIONS]
1. Публикуется ли пакет в публичный индекс? (влияет на приоритет SEC-1: важно vs критично)
2. Есть ли lockfile в репозитории? (влияет на RN-11: важно vs критично)
3. Существует ли src/ layout и tests/? (RN-1, VERIFY)
4. Используются ли streamlit и fastapi в одном процессе? (RN-10)
5. Есть ли CI-конфиг вне материала? (RN-6, VERIFY)

[FUNC:FULL]
- ECON: effort ~0.5 дня (вариант A) / ~2–3 дня (B) / ~5–7 дней (C); cost $0 инфраструктурный (config не создаёт ресурсов); ROI максимальный у A (закрывает 5 из 7 failure points); cost of delay — каждый день без lockfile = риск невоспроизводимой сборки и supply-chain exposure.
- FAIL: критично — пустой wheel при ином layout (RN-1), мажорный апдейт pydantic/openai/fastapi (RN-11), PII leak при публикации (SEC-1); cascade: unpinned → runtime crash → downstream import error; recovery: git revert + yank wheel (не гарантирует отзыв у downstream).
- METRICS: ~50 строк TOML, 17 deps (12 runtime / 3 dev / 2 build), 0 функций, tests configured (pytest), coverage tool отсутствует, observability отсутствует, SLO не заданы.
- ALTERNATIVES: build-backend — setuptools (текущий) / hatchling / poetry-core / flit; lockfile — uv.lock / poetry.lock / pip-tools; extras-split — [ui]/[api]/[llm] vs монолит; license — SPDX-выражение vs license-files.
- EVOLVE: coupling 4/10 (12 внешних deps без границ), abstractions 5/10, feature_add 6/10, module_replace 5/10, overall 5/10 — манифест расширяем, но предсказуемость эволюции снижена отсутствием pinning.
- COMPARE: A — 0.5 дня, $0, low risk, low complexity; B — 2–3 дня, $0, medium risk, medium complexity; C — 5–7 дней, $0, high risk, high complexity (не оправдан без данных о нагрузке).

[MANDATORY BASE]
1. ECONOMICS: time ~0.5 дня (вариант A), cost $0 (config не создаёт облачных ресурсов), при условии что rate не задан и инцидентов не было.
2. RISKS: критично — PII в METADATA при публикации в публичный индекс (SEC-1), ломающие изменения без lockfile (RN-11); важно — unpinned deps (RN-2), невоспроизводимость (RN-8), не-SPDX license (RN-5); при условии подтверждения отсутствия lockfile в репо.
3. INFRASTRUCTURE: pool_size=n/a (config, не сервис), при условии что материал — декларативный манифест.
4. CODE: change ~50 строк pyproject.toml (вариант A), при условии что src/ layout подтверждён.
5. ACTION: now — убрать email (SEC-1); tomorrow — SPDX + pinning + radon→dev; later — CI + lockfile + extras-split.
6. TIMELINE: NOW — PII scrub; TODAY — SPDX, pinning, radon→dev; TOMORROW — lockfile, package-data, wheel check; LATER — CI, dependabot, extras-split.
7. PRODUCTION IMPACT: users N (неизвестно, VERIFY), deploy window — не применимо (config), rollback — git revert (обратимо до публикации wheel).
8. SLO IMPACT: current n/a (SLO не заданы), after n/a, при условии что SLO не определены в материале.
9. CLOUD COST: current $0, projected $0, delta ±$0, при условии что pyproject.toml не создаёт облачных ресурсов.
10. ON-CALL: new alerts — нет (CI не подтверждён), runbook — отсутствует, escalation — не определено (VERIFY).

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | WARN | PII в METADATA (SEC-1), unpinned deps (SEC-3), нет security-сканирования (SEC-2) |
| Facts | OK | Все утверждения выведены из материала; VERIFY-флаги помечены |
| Logic | OK | Противоречий между блоками нет; приоритеты согласованы |
| Applicability | OK | Рекомендации применимы к PEP 621/517 манифесту |
| Effectiveness | OK | Вариант A закрывает 5 из 7 failure points при минимальном diff |
| Resilience | WARN | resilience_score=5/10; нет lockfile, pinning, CI, observability |
| Human factor | WARN | PII автора; нет code review/CI-процесса в материале |
| Clarity | OK | Манифест читаем, структура PEP 621 соблюдена |
| Compliance | WARN | license={text='Private'} не SPDX; нет SBOM-совместимости; PII в METADATA |

[CHANGELOG]
| # | What changed | Reason |
|---|--------------|--------|
| 1 | authors email → role-адрес | Risk High (SEC-1, PII) |
| 2 | license={text} → SPDX | Risk Medium (RN-5, compliance) |
| 3 | deps `>=` → `>=,<` | Risk High (RN-11, breaking changes) |
| 4 | radon runtime → dev | Risk Low (RN-7, footprint) |
| 5 | + package-data whitelist | Risk Medium (SEC-5, integrity) |
| 6 | + uv.lock | Risk High (RN-8, reproducibility) |

[REFLEXION]
1. Слабое место: RN-11 и SEC-1 имеют двойной приоритет (важно/критично) в зависимости от контекста → исправлено: оба помечены с условием (публикация в публичный индекс / наличие lockfile), VERIFY-флаги выставлены.
2. Слабое место: trust boundary runtime→ollama daemon не отражена в threat model stage2 → исправлено: добавлена в [THREAT_MODEL] с пометкой VERIFY.
3. Слабое место: [MANDATORY BASE] п.7 (users N) и п.8 (SLO) без чисел → исправлено: явно указано «неизвестно, VERIFY» и «n/a», без выдуманных значений.
Итог: accepted

---

*Примечание:

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-cd109b
material_hash: sha256:f8b9404602686b74b74495d4ba3db085619015d2988ab18bcb2270699b279808
material_hash_full: sha256:f8b9404602686b74b74495d4ba3db085619015d2988ab18bcb2270699b279808
pii_detected: true
compliance_flags: ['EU AI Act', 'GDPR', '152-ФЗ']
critique_verdict: REQUIRES_REVIEW
risk_verdict: SAFE


[COMPLETENESS]
level: D2
required: 12
missing: []
loss_pct: 0.0%
material_complete: True
verdict: ACCEPTABLE