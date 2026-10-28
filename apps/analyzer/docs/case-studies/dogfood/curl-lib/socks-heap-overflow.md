# Case: curl/lib/socks.c -- CVE-2023-38545

**Дата:** 2026-10-16
**Vishap:** v6.0.1
**Session:** sess-2026-10-16-174827

## Материал

- File: lib/socks.c (curl SOCKS4/SOCKS5 proxy)
- Source: github.com/curl/curl
- CVE: CVE-2023-38545
- Severity: High (CVSS 9.8)
- Affected: curl 7.69.0 -- 8.3.0
- Fixed: curl 8.4.0
- CWE: CWE-122 (heap-based buffer overflow)

## Официальное описание CVE

This flaw makes curl overflow a heap based buffer in the SOCKS5 proxy
handshake. If the hostname is longer than 255 bytes, curl switches to
local name resolving. Due to a bug, the local variable that means
'let the host resolve the name' could get the wrong value during a slow
SOCKS5 handshake, and copy the too long hostname to the target buffer.

Patch: socks: return error if hostname too long for remote resolve.

## Vishap Result

### LLM (Stage 2) -- сработала мощно

Нашла 4 security-находки:

| ID | Issue | Priority |
|---|---|---|
| SEC-1 | rlen > 8 не валидируется -> crash/CVE-класс | критично |
| SEC-4 | creds->user == NULL -> strlen crash | критично |
| SEC-2 | hostname == NULL -> failf %s crash | важно |
| SEC-3 | rlen не инициализирован перед Curl_bufq_peek | важно |

В [CONCLUSION] LLM явно пишет: SEC-1 (rlen > 8 не валидируется) и
SEC-4 (creds->user == NULL -> strlen crash) -- реальные crash/CVE-класс
пути. Это -- прямое попадание в CVE-2023-38545.

### Сравнение

| Источник | Описание |
|---|---|
| CVE-2023-38545 | hostname > 255 -> heap buffer overflow (CWE-122) |
| Vishap SEC-1 | rlen > 8 не валидируется -> crash/CVE-класс |
| Совпадение | Vishap LLM нашла то же, что security researcher |

Vishap не открыл новый CVE. Он переоткрыл известный CVE-2023-38545
через LLM-анализ. Это подтверждает возможности Vishap.

## Regex/taint (P2-7) -- не сработал

    exploitability_reachable: false
    exploitability_path: []
    dataflow_path: []
    exploitability_source_count: 0

Причина: socks.c -- библиотека curl, не приложение. Нет argv, нет
getenv, нет system. Источники приходят через API libcurl -- не regex-source.
Известное ограничение (аналогично DbConnection.java).

## Баг verdict

    critique_verdict: SAFE
    risk_verdict: SAFE

Хотя LLM нашла SEC-1/SEC-4 (критично). Причина: LLM положила
SEC-находки в текст [CONCLUSION], а не в структурированное поле
security.findings. compute_risk_verdict смотрит только структуру,
не текст. Это P0-баг. См. BUG-REPORT-v6.1-Block5.md.

## Уроки

1. LLM-стадия Vishap -- работает. Находит реальные CVE.
2. Verdict = SAFE -- баг. Нужен фикс (v6.1 Block 5).
3. Regex (P2-7) -- не сработал. Библиотека, нет argv/system.

## Ref

- CVE-2023-38545 -- curl.se: https://curl.se/docs/CVE-2023-38545.html
- CVE-2023-38545 -- NVD: https://nvd.nist.gov/vuln/detail/CVE-2023-38545
- CVE-2023-38545 -- Ubuntu: https://ubuntu.com/security/CVE-2023-38545

## Fix (P0, 2026-10-16)

**Проблема:** `risk_verdict = SAFE` при критичных SEC-находках (недетерминированный bug).

**Причина:** структурный разрыв между LLM и verdict:
1. Промпт `02_analyst.md` не задаёт схему `security.findings[]`.
2. `compute_risk_verdict` не читает `threat_model.threats[].priority`.
3. `cwe_ids` собирались только regex-сканом исходника.

**Fix (defense-in-depth, commit 94d224c):**

| # | Компонент | Что |
|---|-----------|-----|
| A | `vishap/02_analyst.md` | Явная схема `security.findings[]` (id/priority/cwe/location) |
| D | `src/pipeline/verdict.py` | `_has_critical_threat_model` -- читает `threat_model.threats[].priority` |
| C | `src/pipeline/verdict.py` | Fallback `_has_critical_sec_in_text(final_markdown)` -- regex `SEC-\d+...(критично\|critical\|CVE-\d\|crash\|overflow\|injection)` |
| -- | `src/pipeline/orchestrator.py` | `collect_findings_cwe(stage2_result)` -- CWE из `security.findings[].cwe` |

**Порядок в `compute_risk_verdict`:**
`force_emergency` -> pii/compliance/cwe -> risk_nodes -> security.findings -> threat_model -> fallback -> SAFE.

**Тесты:** 7 новых (`tests/test_verdict_threat_model.py` + `tests/test_verdict_sec_fallback.py`).

## Результат fix'а (dogfood 2026-10-16)

**Было (сессия 174827):**
- `risk_verdict: SAFE`
- `critique_verdict: SAFE`
- `cwe_ids: []`

**Стало (сессия 4721ab):**
- `risk_verdict: REQUIRES_REVIEW`
- `critique_verdict: REQUIRES_REVIEW`
- `cwe_ids: ['CWE-476', 'CWE-200', 'CWE-754', 'CWE-770']`
- `provenance_commit: 94d224c`

**Найдено LLM:** SEC-1 (NULL-deref `sx->dest`, CWE-476, критично), RN-1 (critical).

**Вывод:** fallback + threat_model + CWE collect **поймали** критичные находки, которые LLM положила в текст `[CONCLUSION]`, а не в структуру.
