# Lessons from upstream contributions

## 2026-10-16 -- curl/curl incident

Context: I ran a Vishap audit on curl docs and submitted 3 issues
(#23438-#23440) directly to github.com/curl/curl. The maintainers
(Daniel Stenberg, Stefan Eissing) responded negatively -- the format
was too long, AI-generated, and not in the contributor's voice.

Actions taken:
- Issues closed by maintainers.
- Replied once with a short human apology.
- Left the project.

Lessons for Vishap users:
1. Never post AI-generated audit output directly to upstream projects.
2. Read CONTRIBUTING.md before filing any issue or PR.
3. Prefer PRs over issues.
4. Keep reports short (<=100 words). Write in your own voice, not the
   tool's.
5. Do not argue with maintainers. They are right by default.
6. If asked to stop -- stop immediately, close, and leave.
7. Vishap is a tool for local analysis / internal review. It is not a
   replacement for human communication.

What changed in the process:
- Added this LESSONS.md.
- Added a note in docs/case-studies/dogfood/curl-docs/README.md.

## 2026-10-16 -- P0 fix: недетерминированный `risk_verdict`

**Bug:** `python -m src.cli analyze socks.c` давал `risk_verdict = SAFE`,
хотя LLM Stage 2 находила критичные SEC-находки (SEC-1..SEC-4) в тексте `[CONCLUSION]`.

**Корень — 2 структурных разрыва:**
1. Промпт `02_analyst.md` не задаёт схему `security.findings[]` (в отличие от `threat_model`).
2. `compute_risk_verdict` читает только `security.findings[]` и `risk_nodes[]`,
   игнорируя `threat_model.threats[].priority` и текст `final_markdown`.

**Почему недетерминированный:** в удачном прогоне LLM кладёт SEC-1 в структуру -> SAFE не воспроизводится.
В багнутом -- в текст / `threat_model` -> SAFE.

**Fix (defense-in-depth, commit 94d224c):**
- **Fix A:** явная схема `security.findings[]` в промпте.
- **Fix D:** `_has_critical_threat_model` -- читает `threat_model.threats[].priority`.
- **Fix C:** fallback `_has_critical_sec_in_text(final_markdown)` -- regex.
- **CWE:** `collect_findings_cwe` -- CWE из `security.findings[].cwe`.

**Уроки:**
1. **Не детерминирован -- не значит "не баг".** Воспроизвести можно перезапуском.
2. **Defense-in-depth для LLM-пайплайнов.** Не полагаться на одну структуру -- LLM нестабильна.
3. **Test-first для fix'а бага.** 7 тестов (граничные: fallback only if structure empty, no false positive).
4. **Dogfood -- доказательство fix'а.** Реальный `socks.c` даёт `REQUIRES_REVIEW` детерминированно.
5. **Fallback -- последний.** Если структура уже даёт critical -- fallback не срабатывает (нет двойного счёта).
6. **Regex не жадный** (`{0,300}?`), иначе false positives.

**Грабли:**
- `Get-Content` в PS 5.1 читает UTF-8 как cp1251 -> `РєСЂРёС‚РёС‡РЅРѕ`. `Get-Content -Encoding utf8` -- правильно.
- `VISHAP_DATA_DIR` обязателен для CLI в песочнице (`~/.vishap/data` заблокирован).
