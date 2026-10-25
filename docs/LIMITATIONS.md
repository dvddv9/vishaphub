# Limitations — Vishap V5.8

**Что Vishap НЕ делает. Honest boundaries.**

---

## 1. Not a compiler, not a runtime

- **Не компилирует** материал.
- **Не запускает** материал.
- **Не проверяет runtime** — только статику.
- **Не гарантирует** heap layout, thread-safety, race conditions.

Что делать вместо:
- `gcc -fsyntax-only file.c` — синтаксис C
- `python -m py_compile file.py` — синтаксис Python
- `go vet ./...` — Go
- `cargo check` — Rust
- ASan/UBSan — runtime memory errors
- fuzz-тесты — граничные случаи

## 2. Truncation

- Материал **усечён до 12 000 символов** (MAX_CHARS).
- Если файл больше — Vishap видит только первые 12 000.
- `material_hash` — hash слайса (первые 12 000).
- `material_hash_full` — hash оригинала (всё, что было).
- `truncated: true` + `original_size: N` — в audit.

Проверка: если `truncated: true`, часть файла **не проанализирована**.

## 3. LLM может ошибаться

- **False positives** — LLM может найти «риск» там, где его нет.
- **False negatives** — LLM может пропустить реальную проблему.
- **Галлюцинации** — LLM может выдумать CWE, которого нет.
- **Калибровка** — `task_type` (review/compliance/other/incident) — эвристика, может ошибиться.

Что делать: проверять критичные находки вручную. VERIFY-пометки в отчётах — маркеры «не проверено».

## 4. Не заменяет тесты, ревью, SAST

- Vishap — **вспомогательный** инструмент, не замена.
- **Не заменяет** unit-тесты.
- **Не заменяет** code review.
- **Не заменяет** детерминированные SAST (Bandit, Semgrep, CodeQL, gosec).
- **Не заменяет** SCA (pip-audit, npm audit, govulncheck).

Что делать: Vishap + SAST + SCA + тесты + ревью = полное покрытие.

## 5. Не имеет network access

- Vishap **не ходит по ссылкам**.
- **Не fetch** SARD/URL — только то, что подано на вход.
- Если материал — «прогони на SARD 501270» — Vishap честно откажется (RN-1: no source code).

Проверка: SARD 501270 case study (`docs/case-studies/hard/sard-501270-metadata-only.md`).

## 6. Не проверяет эксплуатируемость

- **Reachability** — «нашёл SQLi, но достижим ли он извне?» — не проверяет.
- **Blast radius** — «кто пострадает?» — не проверяет.
- **Exploit path** — пошагово «как атакующий дойдёт» — не проверяет.

Что делать: после Vishap — ручной analysis reachability.

## 7. Не имеет SARIF / OWASP mapping / compliance controls

- **SARIF** — стандартный формат для CI (GitHub Code Scanning, Azure DevOps) — не выдаёт.
- **OWASP Top 10** — маппинг CWE → OWASP (A03:2025 Injection) — не делает.
- **Compliance controls** — PCI-DSS Req 6.5.1, GDPR Art. 32 — не маппит на конкретные контроли.

Что делать: конвертировать вручную или добавить post-processor.

## 8. Не sandbox

- Материал **не исполняется** — и с v7.0.0 **не уходит в облако**: единственный LLM-путь — локальный DSH harness (`HARNESS_URL`, по умолчанию `127.0.0.1`).
- Приватный код уходит в облако.
- Для приватных данных — self-hosted OpenAI-совместимый endpoint (`VISHAP_LLM_PROVIDER=custom`).

Что делать: запустить DSH harness и указать `HARNESS_URL` + `HARNESS_TOKEN`. См. `SECURITY.md`.

## 9. PII redaction — не полная

- 15 regex-паттернов для email, phone, passport, snils, iban, aws, Lemon Squeezy, github, slack, google, private_key, password, secret.
- **Не покрыто:** имена, адреса, даты рождения, фотографии, голос, биометрия.
- **Не покрыто:** обфусцированные секреты (base64, hex, rot13).

Что делать: для полной redaction — специализированные tools (Presidio, scrubadub).

## 10. Prompt injection — partial

- `SUBST_MAX_ATTEMPTS = 2` — порог для instruction substitution.
- **Нет семантического** detection («ignore previous instructions»).
- **Нет sandbox** для изоляции LLM.

Что делать: не подавать недоверенный материал в cloud mode без redaction.

---

## Что это значит

**Vishap — не «замена security-инженера».** Vishap — «усилитель»:

| Что | Vishap | Ручной анализ |
|-----|----------|---------------|
| Скорость | 40–90 сек | часы |
| Стоимость | $0.007 | $800/день |
| Multi-material | code, config, spec, data, logs | code |
| Покрытие | LLM + audit | экспертиза |
| Точность | LLM (может ошибаться) | выше |
| Замена тестов | нет | нет |
| Замена ревью | нет | нет |

**Vishap + ручной анализ + SAST/SCA + тесты = полное покрытие.**

---

*Last updated: 2026-10-12 | Vishap V5.8*