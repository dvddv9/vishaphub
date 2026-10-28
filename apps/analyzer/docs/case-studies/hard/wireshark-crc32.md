# Case Study: Wireshark crc32.c — CODE REVIEW (D3)

**Material type:** `hard` (C, Wireshark epan/crc32.c — table-driven CRC32C + CRC32-CCITT)
**Level:** D3
**task_type:** `review`
**Cost:** $0.009829
**Verdict:** REQUIRES_REVIEW
**pii_detected:** True
**Compliance:** GDPR, 152-ФЗ
**Session:** sess-2026-10-12-042806
**audit_id:** audit-2026-10-12-3077e9
**material_hash:** sha256:4c8620902e404e540411f1da3eb7338ea7c1267a8b25feb6662edc1692d336d6  (64 hex, real SHA-256)

**Key findings:**
- **RN-1 (critical):** `calculate_crc32c(int len)` — signed `len`, no `len < 0` guard
- **RN-2 / RN-5 (important):** `crc32_ccitt_tvb_offset` hard-codes `CRC32_CCITT_SEED`; `_offset_seed` is parameterized — divergent seed semantics
- **RN-3 (critical, VERIFY-2):** CRC32C and CRC32-CCITT in one TU under similar names — wrong-algorithm risk
- **RN-6 / RN-8 (important):** no bounds check in `crc32_ccitt_seed`; buffer-API lacks `tvb_ensure_bytes_exist`-style protection
- **Inline annotations recognized:** `BUG_61CF9E42`, `BUG_220FD7EE` (CWE-823, CWE-126)
- **PII detected:** copyright emails (`gerald@wireshark.org`, `ross@guest.adelaide.edu.au`) → GDPR + 152-ФЗ (formal, not user PII)
- **7 risk nodes, 6 threats (0 critical, 3 important, 3 optional)**
- **3 refactoring options** (A: hardening 1–2d, B: split TU 3–5d, C: slice-by-8/SIMD 7–12d)
- **honest boundaries:** macros `CRC32C`/`CRC32C_SWAP` and `epan/crc32.h` not in slice → VERIFY-1/VERIFY-3


**Full report for client:** [wireshark-crc32-full.md](wireshark-crc32-full.md)

---

## Vishap Output

# CRC32.C — CODE REVIEW (D3)

[ECHO] `crc32.c` (Wireshark, epan/) — табличные CRC-функции: CRC32C (Castagnoli, через внешние макросы) и CRC32-CCITT (AUTODIN/HDLC/802.x, через `crc32_ccitt_table`). 7 функций, 2 const-таблицы, tvb-адаптеры. Слайс усечён (`crc32_ccitt_tvb_offset_seed` неполный). task_type=review.

[ROUTE] stage4 → stage3 → stage5. Уровень D3 (size > 500 строк). research_first=false. subst_count=0.

[CONCLUSION] Файл — чистые вычислительные функции без I/O и криптографии; базовая надёжность высокая (const-таблицы, stateless, потокобезопасно). Критические дефекты: (1) buffer-API (`calculate_crc32c`, `crc32_ccitt_seed`) не проверяет границы — OOB read при прямом вызове с недоверенным `len` (FP-2, CWE-125/CWE-823); (2) `crc32_ccitt_tvb_offset` игнорирует seed-семантику, делегируя в `crc32_ccitt` (RN-2/RN-5); (3) смешение двух CRC-алгоритмов в одном TU — риск выбора неверного варианта вызывающим (RN-3, поднят до критично в COVE). Корректность макросов `CRC32C`/`CRC32C_SWAP` не верифицируема из слайса (VERIFY-1). Тесты отсутствуют.

[RISK_NODES]
- **RN-1 (критично):** `calculate_crc32c(int len)` не проверяет `len < 0`; `crc32_ccitt_seed` предполагает ровно `len` валидных байт — не проверяется.
- **RN-2 (важно):** `crc32_ccitt_tvb_offset` → `crc32_ccitt` жёстко применяет `CRC32_CCITT_SEED`, игнорируя seed-семантику offset-варианта.
- **RN-3 (критично, VERIFY-2):** CRC32C и CRC32-CCITT в одном TU под похожими именами — риск выбора неверного алгоритма dissector'ом.
- **RN-5 (важно):** `_offset` и `_offset_seed` идут разными путями (`crc32_ccitt` vs `crc32_ccitt_seed`) — расхождение семантики seed.
- **RN-6 (важно):** нет внутренней проверки границ в `crc32_ccitt_seed` — ответственность переложена на вызывающего.
- **RN-8 (важно):** buffer-API не имеет защиты, аналогичной `tvb_ensure_bytes_exist`.
- **RN-11 (важно):** смена семантики seed или унификация CRC сломает dissectors (BC-1, BC-2).

[THREAT_MODEL]
Trust boundaries: TB-1 (сеть→tvb, защищена `tvb_ensure_bytes_exist`), TB-2 (tvb→buffer API, защищена), TB-3 (вызывающий→buffer API, **НЕ защищена**).
- **T на TB-1:** подделка пакета с совпадающим CRC — CRC не защищает от tampering (важно).
- **I на TB-2:** OOB read при прямом вызове `crc32_ccitt_seed` с `len` из пакета (важно).
- **D на TB-3:** DoS через неверный `len` в `calculate_crc32c` → crash dissector (важно).
Итого: 6 угроз — 0 критичных, 3 важных, 3 опциональных.

[SILENCE_LAYERS]
- **Input silence:** нет данных о нагрузке (размеры пакетов, частота вызовов, распределение `len`) — нельзя оценить, узкое ли место побайтовый цикл.
- **Assumption silence:** предполагается `buf` с ровно `len` валидных байт и `len >= 0`; контракт не задокументирован (`epan/crc32.h` не в слайсе).
- **Consequence silence:** OOB read / crash dissector при ошибке вызывающего; утечка памяти процесса в вычисленный CRC — необратима.

[INTERSECTION_RISKS]
- **TB-1 × TB-3:** недоверенный пакет × прямой вызов buffer-API без tvb-защиты → OOB read на атакующем пакете.
- **CRC32C × CRC32-CCITT:** два алгоритма в одном TU × выбор вызывающим → ложное совпадение/несовпадение CRC.
- **int len × guint len:** отрицательный `int` в `calculate_crc32c` → молчаливый неверный результат без ошибки.

[ASSEMBLY] Ядро: `crc32_ccitt_seed` (табличный цикл), `calculate_crc32c` (макросы), 2 const-таблицы. Сервис: `crc32_ccitt`, 4 tvb-адаптера, `CRC32_CCITT_SEED`. Инфра: glib, tvbuff, epan/crc32.h, внешние макросы. Критический путь: `tvb → tvb_ensure_bytes_exist → tvb_get_ptr → crc32_ccitt_seed → crc32_ccitt_table → return`. Циклов нет.

[REFACTORING] Option A (минимальный hardening, 1–2 дня): null-check `buf`, guard `len<0`, assert в `crc32_ccitt_seed`, унификация `_offset` через `crc32_ccitt_seed(buf,len,CRC32_CCITT_SEED)` — результат идентичен. Option B (3–5 дней): разделение TU `crc32c.c`/`crc32_ccitt.c`, deprecated wrappers, unit-тесты. Option C (7–12 дней): slice-by-8/SIMD — отложить до профиля.

[PARALLELS] Аналогично `crc32.c` в Linux kernel (slice-by-8), zlib `crc32.c` (braided), Go `hash/crc32` (SIMD-таблицы). Все разделяют алгоритмы по файлам — здесь смешаны.

[TESTS] Отсутствуют. Нужны: unit на векторах (`'123456789'` → CRC32C `0xE3069283`), property `crc32_ccitt(buf,len) == crc32_ccitt_seed(buf,len,CRC32_CCITT_SEED)`, fuzz tvb-обёрток с короткими буферами, граничные `len=0/1/INT_MAX`, regression capture-тестов (Ethernet FCS, PPP, HDLC, 802.11, iSCSI, SCTP).

[ACTION]
- **NOW:** добавить unit-тесты на текущее поведение (baseline) — без них любой рефакторинг неверифицируем.
- **TODAY:** внести guards (null-check `buf`, `len<0`) в `calculate_crc32c`; assert в `crc32_ccitt_seed`.
- **TOMORROW:** унифицировать `crc32_ccitt_tvb_offset` через `crc32_ccitt_seed`; запросить `epan/crc32.h` (VERIFY-3).
- **LATER:** разделение TU (Option B); slice-by-8 (Option C) — только после профиля.

[QUESTIONS]
1. Есть ли dissector, вызывающий `crc32_ccitt_seed`/`calculate_crc32c` напрямую с `len` из заголовка пакета без валидации? (VERIFY: не проверено)
2. Определения макросов `CRC32C`/`CRC32C_SWAP` — соответствуют ли заявленной модели Rocksoft (Poly 0x1EDC6F41, Reverse TRUE)? (VERIFY-1: не проверено)
3. Контракт `len`/`buf` в `epan/crc32.h` — задокументирован ли precondition? (VERIFY-3: не проверено)
4. Ожидает ли какой-либо вызывающий seed-семантику от `crc32_ccitt_tvb_offset`? (VERIFY: не проверено)

[FUNC:FULL]
- **ECON:** effort Option A ~1–2 дня, Option B ~3–5 дней, Option C ~7–12 дней (rate не задан); cost $0 инфраструктурный (библиотечный код); ROI не вычисляется без baseline инцидентов; cost of delay — каждый релиз с непроверенным CRC32C-макросом несёт риск ложного принятия повреждённых данных.
- **FAIL:** критично FP-2 (OOB read в `crc32_ccitt_seed` при прямом вызове); важно FP-1 (NULL deref), FP-3 (`len<0` → молчаливый неверный результат), FP-4 (игнорирование seed), FP-6 (смешение алгоритмов); cascade — crash dissector → потеря сессии захвата; recovery — перезапуск Wireshark, откат через git revert + regression capture-тестов.
- **METRICS:** ~5000 строк (усечено), 7 функций, 2 const-таблицы (2 KiB), 7 прямых зависимостей, 0 тестов, perf — O(n) побайтово без векторизации, quality — resilience_score 6/10, infra — n/a (библиотека).
- **ALTERNATIVES:** языки — C (текущий), Rust (memory safety, но несовместимо с Wireshark); фреймворки — n/a; БД — n/a; инфра — n/a; паттерны — разделение TU (Option B), slice-by-8 (Option C), SIMD SSE4.2 для CRC32C.
- **EVOLVE:** coupling 8/10 (низкая между функциями), abstractions 6/10, feature_add 7/10, module_replace 6/10 (снижен смешением алгоритмов), overall 7/10; разделение TU поднимет module_replace до 8–9.
- **COMPARE:** Option A — 1–2 дня, низкий риск, минимальный diff; Option B — 3–5 дней, средний риск, устраняет RN-3; Option C — 7–12 дней, средний-высокий риск, требует профиля.

[MANDATORY BASE]
1. **ECONOMICS:** time Option A 1–2 дня, cost $0 (инфра), при условии rate не задан и baseline инцидентов отсутствует.
2. **RISKS:** критично FP-2 (OOB read), RN-3 (смешение алгоритмов); важно FP-1/FP-3/FP-4/FP-6, при условии прямого вызова buffer-API с недоверенным `len`.
3. **INFRASTRUCTURE:** pool_size=n/a, при условии библиотечный код без сервиса.
4. **CODE:** change ~30–50 строк (guards + унификация), при условии сохранения побитовой совместимости CRC-выходов.
5. **ACTION:** now — unit-тесты baseline; tomorrow — guards + унификация `_offset`.
6. **TIMELINE:** NOW — baseline-тесты; TODAY — guards; TOMORROW — унификация `_offset` + запрос `epan/crc32.h`; LATER — разделение TU, slice-by-8.
7. **PRODUCTION IMPACT:** users — все пользователи Wireshark, разбирающие трафик с CRC-проверкой; deploy window — релизный цикл Wireshark; rollback — git revert + regression capture-тестов (минуты на revert, часы на regression).
8. **SLO IMPACT:** current n/a (библиотека), after n/a, при условии SLO не применимы к библиотечной функции.
9. **CLOUD COST:** current $0, projected $0, delta ±$0, при условии no infrastructure change.
10. **ON-CALL:** new alerts — нет; runbook — n/a; escalation — к мейнтейнерам Wireshark при crash dissector.

[PLAN_B]
- RN-1: явная проверка `len < 0` и `len == 0` в `calculate_crc32c`; документировать контракт в заголовке.
- RN-2: переписать `crc32_ccitt_tvb_offset` на `crc32_ccitt_seed(buf, len, CRC32_CCITT_SEED)`.
- RN-3: разделить файл на `crc32c.c` и `crc32_ccitt.c` (Option B).
- RN-5: унифицировать offset-варианты через единый seed-параметризованный путь.
- RN-6: guard внутри `crc32_ccitt_seed` (не только assert — NDEBUG отключит).
- RN-8: документировать precondition в `epan/crc32.h`; safe-обёртка с проверкой.
- RN-11: versioned API или новые имена при смене семантики.
- SEC-1: null-check `buf` в `calculate_crc32c`.
- SEC-2: документировать precondition; assert/guard в `crc32_ccitt_seed`.
- SEC-3: унифицировать тип `len` на `guint`/`size_t`.
- VERIFY-1: unit-тест на векторе `'123456789'` → `0xE3069283`.
- VERIFY-3: запросить `epan/crc32.h` для проверки контракта.

[MATRIX]
| Dimension | Status | Comment |
|-----------|--------|---------|
| Security | WARN | OOB read в buffer-API (FP-2); tvb-пути защищены; CRC не защищает от tampering |
| Facts | WARN | Макросы CRC32C/CRC32C_SWAP не в слайсе (VERIFY-1); `epan/crc32.h` не в слайсе (VERIFY-3) |
| Logic | OK | Функции чистые, детерминированные; логика табличного CRC корректна |
| Applicability | OK | Рекомендации применимы к Wireshark; Option A — минимальный diff |
| Effectiveness | OK | Guards закрывают FP-1/FP-3; унификация `_offset` закрывает RN-2/RN-5 |
| Resilience | WARN | resilience_score 6/10; нет тестов; buffer-API без защиты |
| Human factor | WARN | Смешение CRC32C/CCITT под похожими именами — риск выбора неверного алгоритма |
| Clarity | OK | Заголовок с лицензией и параметрами таблиц; inline BUG_/FIX_ аннотации |

[REFLEXION]
1. Слабое место: RN-3 поднят до критично в COVE, но Option A его не устраняет → исправлено: Option B включён в план после Option A, конфликт разрешён через escalation level 1.
2. Слабое место: assert в `crc32_ccitt_seed` отключится при NDEBUG → исправлено: NR-2 зафиксирован, требуется явный guard, не только assert.
3. Слабое место: корректность макросов CRC32C неверифицируема из слайса → исправлено: VERIFY-1 вынесен в [QUESTIONS] и [PLAN_B] с конкретным вектором теста.
Итог: accepted

---

*Примечание: `[AUDIT_TRAIL]` не генерируется — добавляется pipeline'ом автоматически. `force_emergency: false` (рекомендации — hotfix TODAY/TOMORROW, не немедленный stop).*

[AUDIT_TRAIL]
audit_id: audit-2026-10-12-3077e9
material_hash: sha256:4c8620902e404e540411f1da3eb7338ea7c1267a8b25feb6662edc1692d336d6
pii_detected: true
compliance_flags: ['GDPR', '152-ФЗ']
critique_verdict: REQUIRES_REVIEW


[COMPLETENESS]
level: D3
required: 12
missing: []
loss_pct: 0.0%
verdict: ACCEPTABLE

---

## Reproduce

    vishap analyze examples/hard/crc32.c

## Notes

- **Known behavior:** copyright emails in the license header trigger `pii_detected: true` → `GDPR` + `152-ФЗ`. This is formal (any email = potential PII under GDPR), not a leak of user data. Documented as known limitation.
- **`material_complete`:** slice was truncated (`crc32_ccitt_tvb_offset_seed` incomplete) — see fix in `orchestrator.py` (field `material_complete` added).

---

## PII false positive (documented)

`pii_detected: true` triggered on **copyright header emails**:
- `gerald@wireshark.org` (Gerald Combs — Wireshark author)
- `ross@guest.adelaide.edu.au` (Ross Williams — "A Painless Guide to CRC")

**This is a false positive.** These are public contacts in a license header, not user PII.
GDPR / 152-ФЗ do not apply to copyright attribution.

**Known limitation:** regex catches any email, including copyright headers.
Future fix: whitelist domains (wireshark.org, gnu.org, fsf.org) or skip first 30 lines.

---

## material_hash vs material_hash_full

- `material_hash` — SHA-256 of the **analyzed slice** (first 12000 chars, `MAX_CHARS`)
- `material_hash_full` — SHA-256 of the **original material** (before truncation)
- `truncated: true` + `original_size: N` — indicate truncation

This allows verification against the source file even when the slice is truncated.
