# Case Study: OpenSSL EVP — Cipher Init Race, Partial-Init, CVE-2023-5363

**Source:** `crypto/evp/evp_enc.c`
**Language:** C
**Level:** D3
**Cost:** $0.009239
**Truncated:** Yes (48012 -> 12000 chars)
**Session:** sess-2026-10-10-144116
**Verdict:** SAFE

---

## Vishap Output

# OpenSSL EVP Cipher Init — D3 Analysis

[ECHO] C-код OpenSSL EVP cipher init path: `EVP_CIPHER_CTX_reset/new/free`, `evp_cipher_init_internal`, `evp_cipher_init_skey_internal`, `EVP_CipherInit_ex2`, `EVP_CipherInit_SKEY`. Вход усечён на INPUT_HINT_LINES (~5000 строк), полный файл недоступен. `subst_count=0`, `research_first=false`, `force_emergency=true` (Stage 4 stop_reason=risk).

[ROUTE] stage0 → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → stage5 (transmitter). Stage 3 не запускался. Stage 4 вернул `return_to_stage2=true` + `force_emergency=true` — 2 критичных конфликта analyst↔synthesizer.

[CONCLUSION] Init-путь функционально корректен для однопоточного использования с обязательным reset после ошибки, но содержит три структурных дефекта: (1) partial-init state без rollback при ошибке `einit/dinit`; (2) отсутствие thread-safety контракта при мутации `ctx` без синхронизации; (3) дублирование init-логики между `evp_cipher_init_internal` и `evp_cipher_init_skey_internal`. Binding-ограничение — FIPS-совместимость — определяет выбор варианта A (minimal hardening) как основного; консолидация (вариант B) откладывается до следующего major.

[RISK_NODES]
- **критично** — Partial-init state: при ошибке `einit/dinit` после аллокации `algctx` и swap `fetched_cipher` ctx сохраняет ресурсы и non-NULL `cipher`. Повторный init без reset → stale состояние.
- **критично** — Thread-safety: `ctx->cipher/algctx/fetched_cipher` мутируются без блокировки. Конкурентный init/reset → race condition, UB, use-after-free.
- **важно** — `skey->skeymgmt->prov` разыменовывается без null-guard → segfault при некорректном skey.
- **важно** — CVE-2023-5363 pre-pass копирует только KEYLEN/IVLEN; комментарий обещает шире, чем код делает.
- **важно** — Coverity suppression `use_after_free` без локального доказательства безопасности refcount-swap.
- **важно** — Дублирование init-логики: любой security-фикс применяется дважды, риск рассинхрона.
- **опционально** — `EVP_CIPHER_fetch` на каждый init при `cipher->prov == NULL` (non-FIPS) — стоимость без кэширования.

[THREAT_MODEL]
- **TB-1** Application → EVP public API: приложение доверяет OpenSSL корректно обработать key/iv/params; OpenSSL доверяет приложению не нарушать thread-safety и lifetime.
- **TB-2** EVP core → Provider callbacks (`einit/dinit/newctx/freectx`): core доверяет провайдеру корректно реализовать callbacks.
- **TB-3** EVP core → `EVP_CIPHER_fetch` (non-FIPS): core доверяет провайдеру вернуть корректный cipher и управлять refcount.
- **TB-4** `EVP_SKEY` → Provider match: `skey->skeymgmt->prov` разыменовывается без null-guard.
- **Top-3 threats**: (D) конкурентный init/reset → UB; (I) partial-init → утечка состояния; (T) NULL `skeymgmt->prov` → segfault.

[SILENCE_LAYERS]
- **Input silence**: нет данных о нагрузке (частота init, число ctx, число потоков) — приоритеты выставлены структурно, не по нагрузке.
- **Assumption silence**: контракт «один ctx — один поток» и «reset после ошибки» не задокументирован и не enforced.
- **Consequence silence**: многопоточные приложения и повторное использование ctx после ошибки → UB/use-after-free/неверная криптооперация; необратимо после утечки данных.

[INTERSECTION_RISKS]
- **concurrency × error_handling**: поток A падает на `einit` после аллокации `algctx`; поток B видит non-NULL `algctx` и переиспользует → смешанное состояние, use-after-free при reset.
- **refcount × error_handling**: `up_ref` + free старого + assign нового `fetched_cipher` до `einit`; при падении `einit` ctx держит ref на новый cipher, но `algctx` может быть от старого.
- **CVE pre-pass × provider callbacks**: провайдер, зависящий от других size-параметров, получит их поздно — аналог CVE-2023-5363 для других параметров.
- **skey path × provider match**: NULL `skeymgmt->prov` → segfault вместо graceful error.

[ASSEMBLY] Слои: public API (`EVP_CipherInit_ex2`, `EVP_CipherInit_SKEY`, `EVP_CIPHER_CTX_new/free/reset`) → internal dispatch (`evp_cipher_init_internal`, `evp_cipher_init_skey_internal`) → provider callback layer (`einit/dinit/*_skey/newctx/freectx`) → provider fetch layer (`EVP_CIPHER_fetch`, `ossl_provider_ctx`). Critical path: `EVP_CipherInit_ex2` → `evp_cipher_init_internal` → cipher null-guard → reset-if-reinit → cipher fallback/fetch → up_ref + swap → `ctx->cipher` assign → pipeline check → `algctx newctx` → NO_PADDING reapply → CVE pre-pass → `einit/dinit` dispatch. Cycles: нет.

[REFACTORING] Вариант A (minimal hardening, рекомендован): null-guard на `skey->skeymgmt->prov`, rollback `algctx/fetched_cipher` при downstream-ошибке, расширение CVE pre-pass, документирование thread-safety контракта. Diff малый, FIPS-совместим, не меняет публичный API. Вариант B (consolidate + harden): объединение двух init-функций — устраняет DRY, но требует FIPS re-certification и большого diff; отложен до следующего major. Вариант C (contract-first): только документация + debug-assert — не закрывает SEC-1.

[PARALLELS] Паттерн «facade + strategy via function pointers + RAII-like lifecycle» — стандартный для OpenSSL provider-архитектуры. Аналогичный partial-init риск встречается в любом коде, где ресурсы аллоцируются до финальной валидации без rollback. Дублирование init-логики — классический случай «copy-paste с расхождением», где комментарий «basically X without Y» маскирует реальные различия.

[TESTS] В слайсе тестов нет. Необходимы: unit lifecycle (new/reset/free), error-path (`einit/dinit` возвращает 0 после частичной мутации — проверить состояние ctx), skey path с NULL `skeymgmt`, TSAN-прогон конкурентного init/reset, fuzz `OSSL_PARAM` inputs, regression CVE-2023-5363 test vectors, provider mock с частичной мутацией. Edge cases: `cipher==NULL && ctx->cipher==NULL`, `cipher->prov==NULL`, `enc==-1`, `iv==NULL`, `skey->skeymgmt->prov==NULL`, повторный init без reset.

[ACTION]
- **NOW**: добавить null-guard на `skey->skeymgmt->prov` (patch_skey_null_guard.c) — устраняет segfault, обратно-совместимо.
- **TODAY**: добавить rollback `algctx/fetched_cipher` при ошибке `einit/dinit` (patch_rollback.c) — закрывает SEC-1; зафиксировать как breaking change в release notes.
- **TOMORROW**: документировать thread-safety контракт + debug-assert на owner thread; расширить CVE pre-pass (требует provider-agnostic registry size-параметров — placeholder не закрывает полностью).
- **LATER**: консолидация init-функций (вариант B) в следующем major с плановой FIPS re-certification.

[QUESTIONS]
1. Подтверждён ли thread-safety контракт `EVP_CIPHER_CTX` в актуальной документации OpenSSL? (COVE flagged: requires_external_verification)
2. Есть ли downstream-зависимости от partial-init state после ошибки? (rollback — breaking change)
3. Какие size-параметры, помимо KEYLEN/IVLEN, ожидают провайдеры до init?
4. Запланирована ли FIPS re-certification на следующий major (определяет возможность варианта B)?

[FUNC:FULL]
- **ECON**: effort — вариант A ~2–3 дня (patch + tests + docs), вариант B ~2–3 недели + FIPS re-certification; cost $0 (библиотечный код, нет cloud); ROI высокий для A (закрывает 2 критичных риска малым diff); budget — не применимо; cloud delta $0; cost of delay — каждый релиз без rollback оставляет partial-init окно в production.
- **FAIL**: критично — partial-init state (SEC-1), конкурентный init/reset (SEC-2); cascade — stale `algctx` → неверная криптооперация → компрометация данных; recovery — обязательный `EVP_CIPHER_CTX_reset` после ошибки (вариант A снимает требование через rollback).
- **METRICS**: codebase — ~6 функций в слайсе, ~47 branch points, nesting_max=4; deps — 15 (внутренние заголовки OpenSSL + libc); tests — 0 в слайсе; perf — `EVP_CIPHER_fetch` на каждый init при `prov==NULL`; quality — Coverity suppression, дублирование логики; infra — N/A (библиотека).
- **ALTERNATIVES**: языки — N/A (C обязателен для OpenSSL core); фреймворки — N/A; БД — N/A; инфра — N/A; паттерны — вариант A (in-place hardening) / B (consolidate) / C (contract-first); binding — FIPS-совместимость → A.
- **EVOLVE**: coupling 4/10 (direct field access, internal headers); abstractions 6/10 (provider callback layer хорош, дублирование снижает); growth 6/10 (новый cipher-режим через provider, но правки в двух init-функциях); friction — дублирование + partial-init + отсутствие thread-safety контракта; overall 5/10.
- **COMPARE**: вариант A — time low, cost $0, risk low, complexity low; вариант B — time high, cost $0 + FIPS re-cert, risk medium, complexity high; вариант C — time low, cost $0, risk low, complexity low, но SEC-1 не закрыт.

[MANDATORY BASE]
1. **ECONOMICS**: time ~2–3 дня (вариант A), cost $0, при условии что FIPS re-certification не требуется для in-place hardening.
2. **RISKS**: критично — partial-init state (SEC-1), конкурентный init/reset (SEC-2); важно — NULL `skeymgmt->prov`, неполный CVE pre-pass, Coverity suppression; при условии однопоточного использования с reset после ошибки — риски не проявляются.
3. **INFRASTRUCTURE**: pool_size=N/A, при условии что это библиотечный код без сервисной инфраструктуры.
4. **CODE**: change ~3 патча (null-guard, rollback, pre-pass), при условии минимального diff без консолидации init-функций.
5. **ACTION**: now — null-guard на `skey->skeymgmt->prov`; tomorrow — rollback + docs + расширение pre-pass.
6. **TIMELINE**: NOW — null-guard; TODAY — rollback; TOMORROW — docs + debug-assert + pre-pass; LATER — консолидация (вариант B) в следующем major.
7. **PRODUCTION IMPACT**: users — миллионы downstream-приложений OpenSSL; deploy window — стандартный minor release; rollback — откат к предыдущей minor-версии, при условии что FIPS-валидация не затронута.
8. **SLO IMPACT**: current N/A, after N/A, при условии что SLO определяется downstream-сервисами, не библиотекой.
9. **CLOUD COST**: current $0, projected $0, delta ±$0, при условии отсутствия инфраструктурных изменений.
10. **ON-CALL**: new alerts — N/A (библиотека); runbook — документировать обязательный reset после ошибки init; escalation — downstream-сервисы, при условии что OpenSSL core не имеет on-call.

[REFLEXION]
1. **Слабое место**: thread-safety контракт `EVP_CIPHER_CTX` основан на внешнем знании, не проверен в слайсе → **исправлено**: помечено как `requires_external_verification` в QUESTIONS и COVE flagged; не утверждается как факт.
2. **Слабое место**: rollback (вариант A) меняет observable state после ошибки — потенциальный breaking change → **исправлено**: зафиксировано в ACTION (release notes) и QUESTIONS (downstream-зависимости); NR-1 в new_risks Stage 4.
3. **Слабое место**: расширение CVE pre-pass требует provider-agnostic registry, которого нет — placeholder не закрывает риск → **исправлено**: помечено как NR-2 (важно), не заявлено как полное решение.
4. **Слабое место**: Stage 4 вернул `return_to_stage2=true` + `force_emergency=true` — 2 критичных конфликта не разрешены в pipeline → **исправлено**: конфликты зафиксированы в COLLISION (Stage 4), binding-ограничение (FIPS) определяет выбор варианта A; escalation level 2 отражён в ROUTE.
5. **Слабое место**: вход усечён — часть файла (`EVP_CipherUpdate/Final`, padding) не проанализирована → **исправлено**: ECHO фиксирует TRUNCATED_INPUT; выводы ограничены слайсом.

**Итог**: accepted (с оговоркой: thread-safety контракт требует внешней верификации; rollback — breaking change, требует release notes).

[AUDIT_TRAIL]
audit_id: audit-2026-10-10-9f955b
material_hash: sha256:f4977957d84b3fdbfeb53e0320ccbe29a94b5b79ead883607d064af02505b6d5
pii_detected: false
compliance_flags: []
critique_verdict: SAFE


[COMPLETENESS]
level: D3
required: 12
missing: []
loss_pct: 0.0%
verdict: ACCEPTABLE

---

## Reproduce

    vishap analyze data/real_cases/hard/openssl_evp_enc.c
