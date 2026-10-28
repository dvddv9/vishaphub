# file-upload-ruby: FULL REPORT

**Полный отчёт pipeline Vishap V5.8.**

---

## Metadata

| Field | Value |
|-------|-------|
| **Session** | `sess-2026-10-12-102015` |
| **audit_id** | `audit-2026-10-12-faa4c2` |
| **material_hash** | `sha256:c6360bf29b044d3a676928c39bd5168c8160520c1ed8a45936a996e90a440c1b` |
| **material_hash_full** | `sha256:c6360bf29b044d3a676928c39bd5168c8160520c1ed8a45936a996e90a440c1b` (original, before truncation) |
| **truncated** | `False` (original_size: 542) |
| **Level** | `D2` |
| **task_type** | `review` |
| **Cost** | `$0.006003` |
| **Verdict** | `SAFE` |
| **Risk verdict** | `EMERGENCY` |
| **pii_detected** | `False` |
| **Compliance** | `none` |

---

## Full Vishap Output (final_markdown)

# File Upload Handler — Security Review

[ECHO] Ruby/Sinatra, ~30 строк, 2 route (`POST /upload`, `GET /read`), 0 тестов, 0 auth, 0 логирования. 5 явных уязвимостей, помеченных в комментариях, но не исправленных. task_type=review, level=D2, session=sess-2026-10-12-XXXXXX.

[ROUTE] stage0 → EMERGENCY_INTERRUPT (RCE, path traversal, arbitrary read) → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). research_first=false, parallel_stages=false.

[CONCLUSION] Код содержит 5 критических уязвимостей с прямым RCE-вектором: отсутствие auth (SEC-1), path traversal (SEC-2), unrestricted upload (SEC-3), chmod 0755 (SEC-4), arbitrary file read (SEC-5). Критический путь атаки: `Client → /upload (no auth) → traversal filename → write → chmod 0755 → exec = RCE`. Требуется немедленное действие СЕГОДНЯ. Нет признаков наличия глобального auth middleware вне фрагмента (VERIFY: не проверено). Нет признаков доступности `uploads/` через внешний web-сервер (VERIFY: не проверено — определяет срочность chmod).

[RISK_NODES]
- RN-1 (критично): нет auth на обоих route — все уязвимости эксплуатируемы анонимно
- RN-2 (критично): `File.join("uploads", filename)` не защищает от `../` и абсолютных путей
- RN-6 (критично): системное избегание всех защитных слоёв (auth, size, type, sanitize, error handling, logging)
- RN-7 (важно): `file[:tempfile].read()` — полная загрузка в память без лимита → OOM/DoS
- RN-8 (важно): нет rescue вокруг FS-операций → 500 без диагностики
- RN-9 (важно): локальный `uploads/` без уникализации имён → коллизии, нет горизонтального масштаба
- RN-10 (важно): параллельные POST с одинаковым filename → перезапись
- RN-3 (важно): дублирование FS-доступа в двух route без общего слоя
- RN-4/RN-5 (важно): комментарии «# BUG N» декларативны, код их не устраняет
- RN-11 (опционально): любое исправление ломает текущий контракт API

[PLAN_B]
- SEC-1 / RN-1: `before`-фильтр Sinatra с проверкой Bearer-токена; deny-by-default для `/upload` и `/read`
- SEC-2 / RN-2: `File.basename(filename)` + `File.expand_path` + проверка префикса `realpath(uploads/)`
- SEC-3 / RN-3: allowlist расширений + magic-bytes проверка + переименование
- SEC-4 / RN-4: `chmod 0644` вместо `0755`; хранить вне webroot
- SEC-5 / RN-5: allowlist путей + auth + realpath-проверка для `/read`
- SEC-6 / RN-6: структурное логирование (кто, что, когда, IP, filename)
- RN-7: стриминг через `IO.copy_stream` с лимитом байт; отказ при превышении
- RN-8: `rescue StandardError` → 500 с логированием; отдельные rescue для ENOENT/EACCES
- RN-9: UUID-префикс имени + вынести `uploads/` в объектное хранилище (S3/MinIO)
- RN-10: запись во временный файл + `File.rename` (atomic) с уникальным именем
- RN-11: версионировать API (`/v2/upload`), оставить `/upload` deprecated с auth

[THREAT_MODEL] 10 угроз, 7 критичных, 3 важных. Trust boundaries: Client→Sinatra (неаутентифицирован), Sinatra→FS (params→File), uploads/→exec (chmod 0755). Top-3: SEC-5 (arbitrary read), SEC-4 (chmod 0755→RCE), SEC-2 (path traversal). STRIDE: S (spoofing filename), T (tampering MIME/traversal), E (elevation via chmod), D (DoS via no size limit), I (info disclosure via /read), R (no audit log).

[SILENCE_LAYERS]
- Input silence: нет данных о нагрузке, размере файлов, окружении (dev/prod) — невозможно оценить DoS-риск
- Assumption silence: предполагается, что filename безопасен и клиент доверенный — нет валидации, нет auth
- Consequence silence: RCE через исполняемый upload, утечка `/etc/passwd`, `.env`, ключей — необратимо

[INTERSECTION_RISKS]
- HTTP × FS: `params → File.join → File.open` без промежуточного слоя → path traversal + arbitrary write в одном шаге
- chmod 0755 × webroot/exec: исполняемые права × HTTP-доступ → RCE
- No auth × GET /read: анонимный доступ × произвольное чтение → полная утечка FS
- No size limit × `.read`: полная загрузка в память × отсутствие лимита → OOM-kill, DoS
- No logging × no auth: нет следов × нет идентификации → инцидент невозможно обнаружить

[ASSEMBLY] Иерархия плоская: core (HTTP routing, FS I/O) и infra (Ruby runtime, host FS, exec context) слиты — HTTP-хендлер напрямую вызывает FS без service-слоя. Это корневая причина всех 5 уязвимостей. Граф зависимостей линейный (циклов нет), что делает атаку одношаговой.

[REFACTORING] Три опции:
- **Option A** (hotfix in-place, 1–2 дня): auth-фильтр + `File.basename` + realpath + chmod 0644 + size limit + rescue. Минимальный diff, но не решает RN-3/RN-9.
- **Option B** (middleware + storage abstraction, 3–5 дней): pipeline auth → size → type → sanitize → store; UUID-имена + atomic rename; S3-ready. Устраняет RN-3, RN-6, RN-9, RN-10.
- **Option C** (kill switch + v2 API, 5–8 дней): немедленно отключить v1, выпустить `/v2/*` с полным pipeline. Ломает всех клиентов.

Рекомендация: Phase 0 (A) сегодня + Phase 2 (B) в течение недели. Не конфликт — последовательность.

[PARALLELS] Паттерн «HTTP-хендлер напрямую вызывает FS» — классический анти-паттерн, встречающийся в CGI-скриптах 2000-х и в современных «быстрых» MVP. Аналог: PHP `move_uploaded_file($_FILES['file']['name'])` без `basename()`. Решение везде одно: слой валидации между транспортом и хранилищем.

[TESTS] 0% coverage. Необходимо:
- unit: `sanitize_filename('../../etc/passwd')` → basename
- unit: `allowed_type?` (magic bytes, extension)
- integration: POST /upload без auth → 401
- integration: POST /upload с `../` → 400
- integration: POST /upload > limit → 413
- integration: GET /read?path=/etc/passwd → 403
- integration: chmod проверка — файл не исполняемый
- concurrency: два параллельных upload → два разных файла

[ACTION]
- **NOW** (сегодня): `chmod 0755 → 0644` (1 строка); добавить `before`-фильтр auth; закрыть `/read` allowlist'ом. Это STOP-класс — не hotfix на 2+ дня.
- **TODAY**: sanitize filename (`File.basename` + realpath-проверка); size limit; rescue вокруг FS-операций; логирование.
- **TOMORROW**: middleware-слой (auth → size → type → sanitize → store); UUID-имена + atomic rename; тесты.
- **LATER**: storage abstraction (S3/MinIO); v2 API; observability (logs/metrics/traces/alerts).

[QUESTIONS]
- Доступен ли `uploads/` через внешний web-сервер (nginx/apache)? (VERIFY: определяет срочность chmod)
- Есть ли глобальный auth middleware вне фрагмента? (VERIFY: не проверено)
- Какое значение `MAX_BYTES` приемлемо? (10 MB — предположение, требует подтверждения владельцем)
- Были ли уже инциденты? (VERIFY: нет логов — проверить внешние источники)
- Есть ли клиенты, полагающиеся на анонимную загрузку/чтение? (влияет на план миграции)

[FUNC:FULL]
- **ECON**: effort Option A 1–2 дня, Option B 3–5 дней, Option C 5–8 дней; cost — rate не задан, ROI не вычисляется без rate; cloud delta 0 (нет инфраструктурного конфига); cost of delay — каждый день без фикса = открытый RCE-вектор + arbitrary read; при инциденте — ротация всех секретов, пересборка образов, возможный простой.
- **FAIL**: критично — FP-1 (`File.open` по несанитизированному пути), FP-2 (`chmod 0755`), FP-3 (`File.read(params['path'])`), FP-4 (нет auth); важно — FP-5 (`.read` в память), FP-6 (нет rescue); cascade: traversal → write → chmod → exec = RCE; recovery: после chmod 0755 + записи в webroot — только внешнее вмешательство (пересборка образа, ротация секретов).
- **METRICS**: codebase ~30 строк, 2 route, 0 функций-хелперов, 0 классов; deps 2 (sinatra, fileutils), нет Gemfile.lock; tests 0% coverage; perf — OOM-риск при больших загрузках; quality — 5 критических уязвимостей; infra — pool_size не применимо (Sinatra single-process; при Puma 5–16 workers), replicas 1 (локальный FS не шарится).
- **ALTERNATIVES**: языки — Ruby (текущий), Go/Rust (лучшая изоляция FS); фреймворки — Sinatra (текущий), Rails (встроенный `ActiveStorage`), Roda; БД — не применимо (нет БД); инфра — локальный FS (текущий), S3/MinIO (рекомендуется); паттерны — middleware pipeline, storage abstraction, deny-by-default.
- **EVOLVE**: coupling 2/10 (прямой доступ к FS из хендлеров); abstractions 1/10 (нет слоёв); growth 2/10 (любое изменение требует правки обоих route); friction высокий — Option B/C поднимают до 6–8.
- **COMPARE**: Option A — 1–2 дня, низкая стоимость, средний риск после, низкая сложность; Option B — 3–5 дней, средняя стоимость, низкий риск, средняя сложность; Option C — 5–8 дней, высокая стоимость, низкий риск, высокая сложность (ломает всех клиентов).

[MANDATORY BASE]
1. **ECONOMICS**: time Option A 1–2 дня, cost $Y (rate не задан — не вычисляется), при условии наличия 1 backend-разработчика; cost of delay — открытый RCE-вектор ежедневно.
2. **RISKS**: критично — SEC-1..SEC-5 (auth, traversal, unrestricted upload, chmod 0755, arbitrary read); важно — RN-7..RN-10 (DoS, no rescue, no unique names, race); при условии, что `uploads/` доступен через web — chmod 0755 = немедленный RCE.
3. **INFRASTRUCTURE**: pool_size не применимо (Sinatra single-process; при Puma 5–16 workers), при условии использования Puma; replicas 1 (локальный FS не шарится).
4. **CODE**: change ~30 строк (полный rewrite app.rb), при условии Option B; минимальный патч Option A — ~10 строк.
5. **ACTION**: now — chmod 0644 + auth-фильтр + закрытие `/read`; tomorrow — sanitize + size limit + rescue + логирование.
6. **TIMELINE**: NOW — chmod 0644, auth-фильтр, закрытие `/read`; TODAY — sanitize, size limit, rescue, логирование; TOMORROW — middleware-слой, UUID-имена, atomic rename, тесты; LATER — storage abstraction, v2 API, observability.
7. **PRODUCTION IMPACT**: users N (не задано — нет данных о нагрузке); deploy window — немедленно (STOP-класс); rollback Option A — revert commit (минуты); rollback после chmod 0755 + записи в webroot — только внешнее вмешательство.
8. **SLO IMPACT**: current N% (SLO не определены); after N% (при добавлении — latency upload, error rate, размер файла p95); при условии определения SLO.
9. **CLOUD COST**: current $N (не задано — нет инфраструктурного конфига); projected $N (не задано); delta ±$0 (no infrastructure change).
10. **ON-CALL**: new alerts — auth_failures_per_minute > 20, traversal_attempts ≥ 1, read_outside_uploads ≥ 1, process_rss_mb > 80%; runbook — отсутствует (требуется создать); escalation — level 0 (0 критичных неразрешённых конфликтов).

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | FAIL | 5 критических уязвимостей, включая RCE-вектор (chmod 0755) и arbitrary read |
| Facts | OK | Все утверждения подтверждены кодом и stage1–4; числа не выдуманы |
| Logic | OK | Критический путь атаки линеен и однозначен; противоречий нет |
| Applicability | OK | Рекомендации применимы к Ruby/Sinatra; Option B реализуем за 3–5 дней |
| Effectiveness | WARN | Option A недостаточен как финальное решение (оставляет RN-3/RN-9) |
| Resilience | FAIL | resilience_score 1/10 — нулевая защита, нет auth, нет валидации, нет логирования |
| Human factor | WARN | Комментарии «# BUG N» без фиксов — признак осознанного оставления уязвимостей |
| Clarity | OK | Уязвимости явно помечены в коде; отчёт структурирован |

[REFLEXION]
1. Слабое место: числа `MAX_BYTES=10 MB` и `pool_size` могли быть восприняты как факты → исправлено: помечены как «требует подтверждения» в [MANDATORY BASE] и [QUESTIONS].
2. Слабое место: `cloud_cost` мог быть выдуман → исправлено: delta 0 с явным reason «no infrastructure change», rate не задан.
3. Слабое место: `[ACTION] NOW` мог рассинхронизироваться с `[MANDATORY BASE] now` → исправлено: обе секции используют NOW/TODAY/TOMORROW/LATER с одинаковым содержимым (chmod 0644 + auth + закрытие /read).
4. Слабое место: `force_emergency: true` мог противоречить «hotfix завтра» → проверено: ACTION NOW = немедленные действия сегодня (STOP-класс), соответствует force_emergency.
5. Слабое место: epistemic hygiene — «config.yaml не подключён» мог быть категоричным → исправлено: «нет признаков наличия глобального auth middleware (VERIFY: не проверено)».

Итог: accepted

---

**Session**: sess-2026-10-12-XXXXXX | **Model**: vishap-v5.8 | **Level**: D2 | **task_type**: review | **force_emergency**: true

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-faa4c2
material_hash: sha256:c6360bf29b044d3a676928c39bd5168c8160520c1ed8a45936a996e90a440c1b
material_hash_full: sha256:c6360bf29b044d3a676928c39bd5168c8160520c1ed8a45936a996e90a440c1b
pii_detected: false
compliance_flags: []
critique_verdict: SAFE
risk_verdict: EMERGENCY


[COMPLETENESS]
level: D2
required: 12
missing: []
loss_pct: 0.0%
material_complete: True
verdict: ACCEPTABLE

---

## Notes

- Full report from `run_pipeline()` in `src/pipeline/orchestrator.py`.
- `final_markdown` length: 12421 chars.
- Source JSON: `data/result_sess-*.json` (in `.gitignore` — this file is the public copy).
- Short version: [file-upload-ruby.md](file-upload-ruby.md)
