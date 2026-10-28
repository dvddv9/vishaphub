# Case Study: packet-btl2cap.c (Wireshark Bluetooth L2CAP dissector)

**Второй dogfood-кейс** после `RequestFilter-java`. Реальный production C-код из Wireshark, прогнанный через Vishap v5.10.5.

## О файле

- **Файл:** `epan/dissectors/packet-btl2cap.c`
- **Источник:** Wireshark (GPL-2.0)
- **Ревизия:** `$Id: packet-btl2cap.c 28412 2009-05-19 17:16:14Z stig $`
- **Год:** 2002-2009
- **Размер:** 44 857 chars (обрезан до 12 000)
- **Строк:** 379 (в слайсе)
- **Язык:** C
- **Роль:** Bluetooth L2CAP protocol dissector

## Метрики анализа (v5.10.5)

| Метрика | Значение |
|---|---|
| Level | **D3** |
| Route | stage4 -> stage3 |
| Cost | **$0.008472** |
| Model | deepseek-chat |
| Tokens in/out | 20 519 / 7 166 |
| Material (analyzed) | 12 000 chars (truncated from 44 857) |
| Truncated | true |
| Completeness | ACCEPTABLE, loss_pct: 0.0% |

## Что Vishap нашёл

**11 risk_nodes** (2 критичных, 6 важных, 3 опционально) + **8 угроз STRIDE**.

### Критичные

| ID | CWE | Риск |
|---|---|---|
| **RN-1** | CWE-125 | `option_length` не валидируется -> over-read за границу tvb |
| **RN-8** | CWE-476 | нет проверки возврата `se_alloc` -> NULL deref при OOM |

### Важные

- **RN-2** (CWE-835): неизвестный `option_type` без skip -> infinite loop.
- **RN-4:** комментарий OR vs mask -- расхождение документации и кода.
- **RN-5:** BUG_68DE1B7B(9) комментарий противоречит коду.
- **RN-6:** нет валидации `option_length` против остатка `length`.
- **RN-9:** неограниченный рост `cid_to_psm_table` -> memory DoS.
- **RN-11:** legacy emem API -- deprecated, lifetime-риски.

### STRIDE (top-3)

- **T (Tampering):** `option_length` не валидируется -> over-read (SEC-1).
- **T:** `config_data` NULL deref (SEC-2).
- **D (DoS):** неизвестный `option_type` -> infinite loop (SEC-3).

### Рекомендации (PLAN_B)

- **Option A** -- minimal hardening (2-3 дня): bounds-check + NULL-check + skip + проверка возвратов.
- **Option B** -- A + emem->wmem (5-8 дней).
- **Option C** -- B + TLV-таблица + единый routing (10-15 дней).

## Senior-level находки

### 1. Reflexion -- самокритика Vishap

> RN-9 изначально помечен опционально, но при враждебном трафике -- memory DoS.
> Исправлено: повышено до важно в [RISK_NODES] и [PLAN_B].

**Это senior-level: Vishap сам пересматривает свою приоритизацию.**

### 2. INTERSECTION_RISKS

> RN-1 x RN-2: невалидированный option_length x неизвестный option_type -> два класса дефектов из одной причины.

### 3. SILENCE_LAYERS

> Input silence: нет данных о нагрузке (частота Connection Request) -> невозможно оценить реальный риск memory DoS.

## Главное -- v5.10.6 fix работает!

Audit trail:

    critique_verdict: REQUIRES_REVIEW
    risk_verdict: REQUIRES_REVIEW
    cwe_ids: ['CWE-476']
    anomaly_verdict: ANOMALIES_FOUND

**До v5.10.6:** risk_verdict: SAFE даже при критичных рисках (баг из dogfood).
**С v5.10.6:** risk_verdict: REQUIRES_REVIEW -- честно.

**Это доказательство фикса на реальном C-коде.**

## НО -- 2 проблемы видны

### Проблема 1: PII false-positive на copyright

    pii_detected: true
    pii_details: {email: 2}
    compliance_flags: [GDPR, 152-ФЗ]

Откуда emails: в шапке copyright Wireshark:

- Copyright 2002, Christoph Scholz <scholz@cs.uni-bonn.de>
- By Gerald Combs <gerald@wireshark.org>

Vishap сработал правильно (нашёл email, redacted перед LLM).
**НО: это ложное срабатывание.** Email в copyright header -- не утечка PII клиента.

**Фикс v5.10.7:** фильтровать email в строках с Copyright/(c)/@wireshark.org.

### Проблема 2: anomaly false-positive на числах из кода

    anomaly_verdict: ANOMALIES_FOUND
    anomaly_count: 2
    anomaly_top:
      - {index: 5, value: 28412.0, score: 16.779, reason: z-score 16.78 > 3.0}
      - {index: 72, value: 8000.0, score: 4.664, reason: z-score 4.66 > 3.0}
    baseline: {mean: 141.09, std: 1684.914}
    samples: 310

Что это:

- 310 чисел в C-коде.
- 28412 -- ревизия `$Id: packet-btl2cap.c 28412`.
- 8000 -- какая-то константа.

**v5.10.6 density guard НЕ сработал** (310 / 12000 = 0.026 > 0.01).

**Фикс v5.10.7:** если std > 10x mean (1684/141 = 11.9x) -> это код, не метрики. Пропустить.

## Файлы

| Файл | Что |
|---|---|
| result_sess-2026-10-14-181153.json | Полный результат |
| otchet-packet-btl2cap.txt | Markdown-отчёт |

## Ссылки

- v5.10.5 release: https://github.com/dvddv9/vishap/releases/tag/v5.10.5
- v5.10.6 release: https://github.com/dvddv9/vishap/releases/tag/v5.10.6
- Wireshark: https://www.wireshark.org/

## Выводы

1. **Vishap работает на production C-коде.** D3, $0.008, 11 рисков, CWE-125/476/835/252.
2. **v5.10.6 risk_verdict fix работает** на C-коде (REQUIRES_REVIEW, не SAFE).
3. **2 false-positive:** PII на copyright, anomaly на числах кода.
4. **Этот кейс -- триггер для v5.10.7.**
5. **Второй production-кейс** после RequestFilter.java.
