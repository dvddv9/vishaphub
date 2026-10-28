# Case Study: File Upload (Ruby/Sinatra) — Path Traversal, RCE, Arbitrary Read

**Language:** Ruby
**Level:** D2
**Cost:** $0.005519
**Verdict:** SAFE
**Session:** sess-2026-10-10-153605
**Bugs planted:** 5 — Path traversal, No auth, No size/type check, chmod 0755, Arbitrary read
**Bugs found:** 10
**False positives:** 0

**Key findings:** 4 критичных вектора в 30 строках: path traversal, arbitrary read, executable upload (RCE), no auth. STRIDE 8/8. Incident plan: kill switch → audit → rotation → hardening.


**Full report for client:** [file-upload-ruby-full.md](file-upload-ruby-full.md)

---

## Vishap Output

# [EMERGENCY] Sinatra File Upload Handler — RCE + Arbitrary File Read

**force_emergency: true** — активная эксплуатация возможна анонимно. Действие немедленно.

---

## [ECHO]

Материал: ~30 строк Ruby/Sinatra. Два эндпоинта: `POST /upload` (запись файла по user-controlled пути + `chmod 0755`) и `GET /read` (`File.read(params["path"])`). Комментарии `BUG 1..5` аннотируют дефекты, код их не устраняет. Auth, валидация, лимиты, логирование — отсутствуют полностью. Уровень D2, но EMERGENCY_INTERRUPT переопределяет маршрутизацию.

## [ROUTE]

stage0 → stage1 → stage2 → stage4 → **stage5 (transmitter)**. `return_to_stage2: true` (2 критичных конфликта Analyst/Researcher), `force_emergency: true`. Stage3 пропущен (emergency override).

## [CONCLUSION]

Код содержит **4 независимых критических вектора** в 30 строках: path traversal, arbitrary file read, executable upload (RCE-вектор), отсутствие auth. Комментарии `BUG 1..5` — признание дефектов без митигации. Это не техдолг — это активная уязвимость в проде. **Немедленно: kill switch (Option C) → аудит → ротация секретов → hardening (Option A) → object storage (Option B).**

## [RISK_NODES]

| # | Узел | Приоритет | Суть |
|---|------|-----------|------|
| 1 | Неявное допущение | критично | `uploads/` предполагается вне web root — не проверено |
| 5 | Внутреннее противоречие | критично | Комментарии BUG без митигации |
| 6 | Стратегическое избегание | критично | Систематическое отсутствие всех защитных слоёв |
| 2 | Слабое обобщение | важно | Любой multipart трактуется как доверенный |
| 7 | Производительность | важно | `tempfile.read()` без лимита → OOM |
| 8 | Надёжность | важно | Нет rescue, нет cleanup |
| 9 | Масштабируемость | важно | Локальный диск, коллизии имён |
| 10 | Конкурентность | важно | Last-writer-wins, TOCTOU |
| 4 | Сдвиг тезиса | важно | «Черновик» подменяет «прод-обработчик» |
| 3 | Конкурирующая реализация | опционально | Rack::Protection обойдён |
| 11 | Ломающие изменения | опционально | Auth сломает анонимных клиентов |

## [THREAT_MODEL]

**Trust boundaries:** клиент→HTTP (×2), HTTP→ФС.

| STRIDE | Угроза | Приоритет | Митигация |
|--------|--------|-----------|-----------|
| S | Нет auth — аноним действует как легитимный | критично | Сессия/токен + RBAC |
| T | Path traversal `../../etc/cron.d/x` | критично | basename + allowlist + prefix check |
| E | `chmod 0755` → RCE при web-served | критично | Убрать chmod, 0640, вне web root |
| I | Arbitrary read `../../etc/passwd` | критично | Удалить эндпоинт / allowlist + auth |
| D | DoS: неограниченный upload → OOM | важно | Rack::Multipart limit, квота |
| T | Symlink swap (TOCTOU) | важно | O_NOFOLLOW, chmod по fd |
| R | Нет audit log | важно | Структурированный лог |
| S | CSRF на POST | важно | CSRF-токен, SameSite |

**Top-3:** arbitrary file read → path traversal + chmod → отсутствие auth (усилитель).

## [SILENCE_LAYERS]

- **Input silence:** нет данных о нагрузке, размере файлов, окружении (web root vs. вне).
- **Assumption silence:** «uploads безопасен, клиенты доверенные» — неявно, не проверено.
- **Consequence silence:** RCE + утечка секретов — **необратимо**; ротация ключей не отменяет уже случившийся доступ.

## [INTERSECTION_RISKS]

1. **HTTP → ФС:** params напрямую становятся путями — нет буфера между слоями.
2. **chmod 0755 + web-served uploads:** загрузка → исполнение, полный RCE-цикл без доп. условий.
3. **GET /read + POST /upload:** write + read произвольных путей в одном сервисе — комбинированный вектор.
4. **Нет auth + нет rate limit:** анонимная массовая эксплуатация без сигнала обнаружения.

## [ASSEMBLY]

**Иерархия плоская:** core (route handlers, FS primitives) и infra (локальный диск, процесс) слиты. Service-слой валидации/auth отсутствует — корневой дефект структуры.

**Critical path:** `client → POST /upload → params → File.join → File.open → chmod 0755 → (web-served) → RCE`. Граф линейный, циклов нет — атака детерминирована: один запрос = одна операция ФС.

**Point of no return:** `File.open(path, "wb")` — материализация произвольного пути на диске.

## [REFACTORING]

**Option A — Hardening in-place (S, risk→средний):** auth, basename+allowlist, size limit, type allowlist, убрать chmod, 0640, вне web root, O_NOFOLLOW. Минимальный diff, но локальный диск и GET /read остаются.

**Option B — Object storage + signed URLs (L, risk→низкий):** S3/GCS, presigned PUT/GET, auth обязателен, метаданные в БД. Устраняет класс уязвимостей. Breaking change + новая инфра.

**Option C — Kill switch (XS, risk→нулевой):** немедленно отключить оба эндпоинта, аудит, ротация. Обязателен при подозрении на компромисс.

**Фазы:** C (немедленно) → A (1–2 дня) → B (1–2 недели).

## [PARALLELS]

Rack::Protection и Rack::Multipart решают часть задач (CSRF, size limit, multipart parsing). **Не отменяют** необходимость auth и sanitization — дополнение, не замена. Sinatra DSL обойдён ручным `File.open` — дублирование функциональности без защитных слоёв фреймворка.

## [TESTS]

**Coverage: 0%.** Необходимо:
- Unit: sanitization (traversal, null byte, unicode, empty), size limit, type allowlist.
- Integration: auth required на обоих эндпоинтах, /read ограничен allowlist.
- Security: symlink swap, TOCTOU.
- Fuzz: filename и path.

**Edge cases:** `../../etc/passwd`, `a\x00.rb`, `''`, `/etc/shadow`, `/proc/self/environ`, огромный файл, одновременная загрузка одинакового имени.

## [ACTION]

**NOW (немедленно):**
1. Kill switch — отключить `POST /upload` и `GET /read`.
2. Аудит `uploads/` — сканирование на executable, traversal-имена, хэши.
3. Ротация секретов (ключи, конфиги, БД-креды).
4. Проверка на persistence (cron, systemd, authorized_keys).

**TODAY:**
5. Внедрить auth (реальную, не заглушку).
6. Sanitization: basename + allowlist расширений + prefix check.
7. Убрать `chmod 0755`, права 0640, хранить вне web root.

**TOMORROW:**
8. Size limit (10 MB), type allowlist, timeout 10s.
9. Audit log, метрики, алерты.
10. Тесты (unit + integration + security).

**LATER:**
11. Миграция на object storage (Option B).
12. SLO, on-call, runbook.

## [QUESTIONS]

1. **VERIFY:** отдаётся ли `uploads/` статикой web-сервером? (определяет, критичен ли chmod как RCE или только локальная эскалация)
2. **VERIFY:** привилегии процесса Sinatra — root или непривилегированный?
3. **VERIFY:** есть ли `Gemfile.lock` и CVE в sinatra?
4. **VERIFY:** реальный объём загрузок (для оценки cost Option B)?
5. Есть ли клиенты, полагающиеся на текущее поведение (абсолютные пути, анонимный доступ)?

---

## [FUNC:FULL]

**ECON:** effort — Option C: XS (немедленно, $0); Option A: S (1–2 дня, ~$0); Option B: L (1–2 недели, cost S3 не оценён — нет данных об объёме). Cost of delay: **необратим** — каждый час экспозиции = потенциальный RCE + утечка секретов. ROI немедленного kill switch: максимальный.

**FAIL:** критично — `File.open(path, "wb")` (point of no return), `chmod 0755` (RCE-вектор), `File.read(params["path"])` (утечка), отсутствие auth (усилитель). Cascade: анонимный клиент → произвольная запись → исполнение → компромисс хоста. Recovery: kill switch → аудит → ротация → проверка persistence. Откат кода **не отменяет** уже загруженные файлы и утёкшие данные.

**METRICS:** codebase ~30 строк, 2 route, 0 helper. Deps: sinatra, fileutils (stdlib). Tests: 0% coverage. Perf: `tempfile.read()` без лимита → OOM при большом файле. Quality: 5 self-labeled BUG, 0 митигаций. Infra: локальный диск, pool_size=50 (при условии I/O-bound), memory 512 MB (при лимите 10 MB × 50 воркеров), replicas=1 (локальный диск).

**ALTERNATIVES:** языки — n/a (Ruby задан). Фреймворки — Rack::Protection, Rack::Multipart (дополнение, не замена). БД — Option B: метаданные в БД (files: id, key, owner_id, content_type, size, sha256, created_at). Инфра — Option B: S3/GCS + presigned URLs. Паттерны — atomic write (tempfile + rename), O_NOFOLLOW, Idempotency-Key.

**EVOLVE:** coupling 2/10 (handlers напрямую связаны с ФС и params). Abstractions 1/10 (DIP нарушен, нет абстракций). Feature_add 2/10 (любая фича требует правки тела хендлера). Module_replace 3/10 (замена ФС на object storage = переписывание обоих хендлеров). Overall 2/10.

**COMPARE:** Option A — time S, cost ~$0, risk→средний, complexity низкая. Option B — time L, cost S3 (не оценён), risk→низкий, complexity высокая. Option C — time XS, cost $0, risk→нулевой (но функциональность отсутствует), complexity нулевая. **Рекомендация: C → A → B.**

---

## [MANDATORY BASE]

1. **ECONOMICS:** time — C: немедленно, A: 1–2 дня, B: 1–2 недели; cost — C/A: ~$0, B: S3 (не оценён, нет данных об объёме); при условии, что объём загрузок неизвестен (input_silence).
2. **RISKS:** критично — path traversal, arbitrary read, executable upload (RCE), отсутствие auth; важно — DoS (OOM), TOCTOU, нет audit log, CSRF; при условии, что `uploads/` отдаётся статикой (VERIFY) — chmod 0755 = RCE, иначе — локальная эскалация.
3. **INFRASTRUCTURE:** pool_size=50, при условии I/O-bound нагрузки; memory 512 MB, при условии лимита 10 MB на файл × 50 воркеров; replicas=1, при условии локального диска (Option A); autoscaling=false, при условии отсутствия метрик.
4. **CODE:** change — полная замена обоих хендлеров (см. code_generation); при условии, что auth-заглушка (`HTTP_AUTHORIZATION` не пустой) **не должна** деплоиться как рабочая.
5. **ACTION:** now — kill switch + аудит + ротация секретов; tomorrow — auth + sanitization + убрать chmod + size/type limit.
6. **TIMELINE:** NOW — kill switch, аудит, ротация; TODAY — auth, sanitization, chmod removal; TOMORROW — size/type limit, audit log, тесты; LATER — object storage (Option B), SLO, on-call.
7. **PRODUCTION IMPACT:** users — все анонимные клиенты (неограниченно); deploy window — немедленно (emergency); rollback — откат кода не отменяет загруженные файлы и утёкшие данные, требуется аудит + ротация.
8. **SLO IMPACT:** current — SLO не определены (0%); after — availability 99.9%, p99 latency <5s, error rate <1%, при условии внедрения метрик и алертов.
9. **CLOUD COST:** current $0, projected $0 (Option A/C), delta ±$0; Option B — delta не оценён (нет данных об объёме загрузок).
10. **ON-CALL:** new alerts — executable_files_in_uploads >0, read_requests_outside_allowlist >0, disk_usage >85%, auth_failure_rate >100/min; runbook — kill switch, аудит, ротация; escalation — security engineer + владелец сервиса.

---

## [REFLEXION]

1. **Слабое место:** auth-заглушка в сгенерированном коде (`HTTP_AUTHORIZATION` не пустой) может быть задеплоена как «рабочая». → **Исправлено:** явный TODO + зафиксировано в `new_risks` (критично) + требование теста, падающего при отсутствии реальной auth.
2. **Слабое место:** предположение, что `uploads/` вне web root — не проверено, влияет на критичность chmod 0755. → **Исправлено:** зафиксировано в `silence_layers.assumption_silence` + `cove.flagged` (VERIFY) + в `[QUESTIONS]` п.1.
3. **Слабое место:** конфликт между рекомендациями (C немедленно vs. A hardening) — несовместимы по времени. → **Исправлено:** разрешено через фазы C → A → B в `[REFACTORING]` и `[ACTION]`.

**Итог:** accepted.

---

*Audit trail добавляется pipeline'ом автоматически.*

[AUDIT_TRAIL]
audit_id: audit-2026-10-10-af2d27
material_hash: sha256:52685edef8d065aa9e08cca2a14830ae0d0ae822ba829818a8fa165e31246c94
pii_detected: false
compliance_flags: []
critique_verdict: SAFE


[COMPLETENESS]
level: D2
required: 12
missing: []
loss_pct: 0.0%
verdict: ACCEPTABLE

---

## Reproduce

    vishap analyze data/real_cases/own/file_upload.rb
