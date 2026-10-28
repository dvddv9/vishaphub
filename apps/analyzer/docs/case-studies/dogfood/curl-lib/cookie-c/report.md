VISHAP V5.8 — STAGE 5: TRANSMITTER
Session: sess-2026-10-17-195421 · Level: D3 · Task: review · Material: curl cookie.c (C, truncated slice)

[ECHO]
Слайс cookie.c из curl: парсинг, нормализация, хранение, матчинг и жизненный цикл cookie. Файл обрезан посреди parse_first_pair — полный контроль потока не оценивается. Язык C не покрыт tree-sitter путём; все выводы — ручное чтение. Задача: code review с фокусом на безопасность и конкурентность.

[ROUTE]
stage4 (синтез) → stage3 (сборка). Последовательный маршрут, без параллельных стадий. subst_count=0, подмен не обнаружено.

[CONCLUSION]
Код зрелый, с RFC-комментариями и early-exit оптимизацией, но несёт один критический риск (гонка на общем CookieInfo при отсутствии видимой синхронизации — SEC-3) и два важных (обход валидации октетов через встроенный NUL — SEC-1; отсутствие bounds-check на cp[COOKIE_PIECES] — SEC-2, VERIFY). Критический риск зависит от невидимого контракта share-lock, который в слайсе не выражен — no signs of lock enforcement found (VERIFY: curl_share.c не в слайсе). Рекомендация: Option A (contract-hardening) как фаза 1, затем Option B (defensive parser).

[RISK_NODES]
IDПриоритетСуть
RN-1 / SEC-3критичноremove_expired/storecookie мутируют ci->numcookies/next_expiration и co без видимой синхронизации. Безопасность целиком на невидимом контракте share-lock.
RN-2 / SEC-1важноinvalid_octets: while(len && *p) обрывается на NUL — хвост буфера не валидируется.
RN-6 / SEC-2важно (VERIFY)storecookie индексирует cp[0..3] без проверки размера массива — OOB-чтение при нарушении контракта.
RN-8 / SEC-4важноstorecookie при OOM оставляет co частично заполненным; корректность зависит от freecookie у caller.
RN-4важноКомментарий RFC6265 4.1.1 обещает cookie-octet диапазон, код фильтрует только control bytes — документационный долг.
RN-3 / RN-5опциональноpathmatch осознанно отклоняется от RFC6265 5.1.4; инвариант пути держится на соглашении.
RN-7опциональноpathmatch вызывает strlen(uri_path) дважды на горячем пути.
RN-9опциональноremove_expired — O(N) по бакетам при массовом истечении.
RN-11опциональноcap_expires меняет expires до 400 дней — поведенческое изменение.

[PLAN_B]
SEC-3 (гонка): DEBUGASSERT(lock_held) в remove_expired/storecookie + документирование контракта в cookie.h; при срабатывании assert в тестах — переход к Option C (lock wrapper).
SEC-1 (NUL-обрыв): переписать invalid_octets на полный проход len с явным отклонением 0x00.
SEC-2 (bounds): DEBUGASSERT(cp) + комментарий-контракт; при недоверенном caller — передавать длину массива.
SEC-4 (OOM): goto fail с freecookie(co, FALSE) при ошибке в storecookie.
RN-4 (doc mismatch): привести комментарий к фактической фильтрации или расширить фильтр — решить явно.

[THREAT_MODEL]
КомпонентГраницаSTRIDEУгрозаПриоритет
cookie parserHTTP header → parserTИнъекция через невалидированные октеты (NUL обходит проверку)важно
cookie storeHTTP header → parserSПодмена домена через tailmatch-обход (evil-example.com)важно
cookie jarjar → параллельные потокиTПорча общего состояния при гонкекритично
cookie jarjar → параллельные потокиDDoS через массовое истечение (O(N) под блокировкой)опционально
cookie parserHTTP header → parserIУтечка cookie-значений в логах (infof)опционально
cookie storeHTTP header → parserEЭскалация через path-match (/admin → /administrator)важно

Итого: 6 угроз — 1 критическая, 3 важных, 2 опциональных.

[SILENCE_LAYERS]
Input silence: нет цифр нагрузки — размер jar, частота истечения, число потоков. Нельзя оценить критичность O(N) эвикции.
Assumption silence: «caller всегда держит share lock и вызывает freecookie при ошибке» — контракт не выражен ни типом, ни assert, ни комментарием.
Consequence silence: порча cookie jar → отправка чужих cookie — необратимо с точки зрения приватности.

[INTERSECTION_RISKS]
assumption_silence × concurrency: неявный контракт блокировки × отсутствие видимой синхронизации → гонка проявляется только под нагрузкой и только при shared jar — самый опасный класс багов.
input_silence × consequence_silence: нет цифр нагрузки × необратимая порча jar → нельзя приоритизировать фикс, а последствие необратимо; потеря выше риска.

[ASSEMBLY]
Слайс собран из 14 static-хелперов, разложенных по 5 слоям: parsing (parse_first_pair, invalid_octets), normalization (sanitize_cookie_path, cap_expires), storage (storecookie, strstore), matching (cookie_tailmatch, pathmatch, cookiehash, get_top_domain), lifecycle (freecookie, remove_expired). Когезия высокая, связность умеренная (17 внутренних заголовков curl).

[REFACTORING]
Option A (contract-hardening): assert lock-held + bounds-check + фикс NUL-цикла. 2–3 дня, минимальное поведенческое изменение.
Option B (defensive parser): полная валидация len, fuzz-корпус, OOM-safe storecookie. 4–6 дней.
Option C (concurrency-first): lock wrapper API в curl_share. 8–12 дней, лучший долгосрочный результат.

[PARALLELS]
invalid_octets vs RFC6265 4.1.1 — фильтр уже́ заявленного диапазона (осознанно, но NUL-обрыв — баг).
pathmatch vs RFC6265 5.1.4 — осознанное отклонение, вторая семантика path-match.
cap_expires vs RFC6265bis draft-19 — кэп 400 дней, выравнивание на 60-секундную границу.

[TESTS]
unit: invalid_octets с встроенным NUL
unit: cookie_tailmatch границы домена (evil-example.com)
unit: pathmatch граница /
unit: storecookie OOM → cleanup
concurrency: shared jar под потоками
fuzz: парсер cookie
Покрытие по слайсу не оценивается (тесты вне слайса).

[ACTION]
NOW: добавить DEBUGASSERT(lock_held) в remove_expired/storecookie + документировать контракт в cookie.h (фаза 1 Option A).
TODAY: фикс invalid_octets — полный проход len, явное отклонение 0x00.
TOMORROW: storecookie cleanup-on-error (goto fail → freecookie); bounds-check cp[COOKIE_PIECES].
LATER: fuzz-корпус + concurrency-тесты (Option B); при срабатывании assert — Option C.

[QUESTIONS]
Держит ли caller share lock вокруг remove_expired/storecookie? (VERIFY: curl_share.c не в слайсе)
Может ли caller передать cp с числом элементов < COOKIE_PIECES? (VERIFY: контракт не выражен типом)
Persistence jar → диск — отдельная trust boundary, не покрыта слайсом. Нужен отдельный слайс?
Приемлемо ли ужесточение invalid_octets (дроп ранее принятых cookie) для потребителей?

[FUNC:FULL]
ECON: effort 2–3 дня (Option A) / 4–6 (B) / 8–12 (C); cost $0 cloud (библиотека, stdlib-only); ROI высокий для A — 2–3 дня устраняют критическую гонку + NUL-обход; cost of delay асимметричен (необратимый privacy-риск при каждом релизе).
FAIL: критично — remove_expired без блокировки (гонка на numcookies/next_expiration); важно — invalid_octets NUL-обрыв, storecookie OOM partial state, cookie_tailmatch граница домена; cascade: гонка → порча jar → отправка чужих cookie; recovery: откат cookie.c к предыдущему тегу, изменения локальны.
METRICS: codebase — 14 static-хелперов, 5 слоёв, nesting_max 4; deps — 17 внутренних заголовков; tests — вне слайса, не оценивается; perf — O(len) парсинг, O(N) эвикция с early-exit; quality — resilience_score 6/10; infra — n/a (библиотека).
ALTERNATIVES: Option A (assert + bounds + NUL-фикс, 2–3 дня) / Option B (defensive parser + fuzz, 4–6 дней) / Option C (lock wrapper API, 8–12 дней); языки/фреймворки/БД — n/a (C-библиотека).
EVOLVE: coupling 5/10 (умеренная связность с curl internals); abstractions 6/10; feature_add 7/10; module_replace 6/10; overall 6/10 — главный тормоз эволюции: невидимый lock-контракт.
COMPARE: A — 2–3 дня, низкий риск, минимальное изменение; B — 4–6 дней, средний риск, строже поведение; C — 8–12 дней, высокий риск (API), структурное устранение гонки.

[MANDATORY BASE]
ECONOMICS: time 2–3 дня (Option A), cost $0 cloud, при условии что фикс локален в cookie.c и не требует ABI-изменений.
RISKS: критично — гонка на CookieInfo (SEC-3); важно — NUL-обход (SEC-1), bounds-check (SEC-2, VERIFY), OOM partial state (SEC-4); при условии что caller не держит share lock (VERIFY).
INFRASTRUCTURE: pool_size=n/a (библиотека, нет пула соединений), при условии что это C-библиотека, а не сервис.
CODE: change ~3 функции (invalid_octets, storecookie, remove_expired), при условии DEBUG-only assert (без ABI-break).
ACTION: now — assert lock-held + doc; tomorrow — NUL-фикс + cleanup-on-error.
TIMELINE: NOW — assert + doc; TODAY — invalid_octets; TOMORROW — storecookie cleanup + bounds; LATER — fuzz + concurrency-тесты.
PRODUCTION IMPACT: users — все потребители curl с HTTP+cookies; deploy window — обычный релизный цикл curl; rollback — откат cookie.c к предыдущему тегу, изменения локальны.
SLO IMPACT: current n/a (библиотека, SLO у потребителей), after n/a, при условии что SLO определяется на уровне приложения-потребителя.
CLOUD COST: current $0, projected $0, delta ±$0 — нет инфраструктурных изменений.
ON-CALL: new alerts — n/a (OSS-библиотека, on-call у потребителей); runbook — changelog-запись о поведенческом изменении invalid_octets/cap_expires; escalation — при срабатывании assert в тестах → Option C.

[MATRIX]
DimensionStatusComment
SecurityFAILSEC-3 гонка (критично), SEC-1 NUL-обход (важно)
FactsWARNСлайс обрезан; share-lock контракт не подтверждён (VERIFY)
LogicOKВыводы согласованы между stage1–4; COVE флаги учтены
ApplicabilityOKOption A применим немедленно, локален
EffectivenessOK2–3 дня устраняют критический риск
ResilienceWARNresilience_score 6/10; зависимость от невидимого контракта
Human factorWARNНеявный контракт → ошибки caller'ов; нужен assert + doc
ClarityOKRFC-комментарии обширны; RN-4 doc mismatch — долг

[REFLEXION]
Слабое место: SEC-2 помечен «важно», но stage2 COVE предлагал повысить до критично → исправлено: оставлен «важно (VERIFY)» с явной пометкой о расхождении second_opinion (security engineer downgrades) и условием проверки caller-контракта.
Слабое место: риск гонки мог быть ложным (lock вне слайса) → исправлено: везде добавлен (VERIFY: curl_share.c не в слайсе), категоричное «гонка есть» заменено на «no signs of lock enforcement found (VERIFY)».
Слабое место: ACTION и MANDATORY BASE могли рассинхронизироваться по шкале → исправлено: обе секции используют NOW/TODAY/TOMORROW/LATER с одинаковыми действиями.
Итог: accepted

[AUDIT_TRAIL] generator: Vishap V6.0.1 audit_id: audit-2026-10-17-50f758 material_hash: sha256:090701b94535c430616f0cb6e5499f88b938b73fbadfea907821a75a1a142e47 material_hash_full: sha256:dae0b75dceb70772537d47e4c51e93cdf07b76561231e443316edb3041f1daa2 pii_detected: false compliance_flags: [] compliance_controls: {} compliance_standards: [] critique_verdict: REQUIRES_REVIEW risk_verdict: REQUIRES_REVIEW cwe_ids: ['CWE-20', 'CWE-125', 'CWE-362', 'CWE-459'] owasp_categories: ['Memory Safety'] exploitability_reachable: False exploitability_auth_required: False exploitability_blast_radius: none exploitability_source_count: 0 exploitability_path: [] dataflow_path: [] dataflow_source_count: 0 anomaly_verdict: NORMAL anomaly_count: 0 anomaly_method: none anomaly_top: [] provenance_source: git/main provenance_commit: 2b72416

[COMPLETENESS] level: D3 required: 12 missing: [] loss_pct: 0.0% material_complete: False verdict: ACCEPTABLE
