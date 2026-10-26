# Changelog

All notable changes to Vishap. Format based on [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Security
- **SAML guard is fail-closed**: `validate_saml_assertion` rejects every assertion until real signature/audience/issuer verification exists (it used to return `True`).
- **CORS**: removed the `*.vercel.app` / `*.onrender.com` / `*.fly.dev` wildcards (anyone can register a subdomain there). Loopback and the desktop shell stay allowed; list your own deployed UI in `VISHAP_CORS_ORIGINS` (comma-separated exact origins). **Deployments with a hosted UI must set it.**
- **Rate limiter**: client IP honours `X-Forwarded-For` only when `VISHAP_TRUSTED_PROXY_HOPS` is set (Render: `1`), counted from the right so a spoofed leftmost value is ignored; expired buckets are swept so memory no longer grows.

### Added
- **Bring-your-own LLM key**: the key a user enters in the UI (`X-LLM-Api-Key`) is now actually used by `/analyze`, `/analyze/async` and `/analyze/batch`. With `VISHAP_REQUIRE_USER_LLM_KEY=1` the server's own `CUSTOM_LLM_KEY` is never used (requests without a key get 401). A caller key stays in-process and is never put on the Celery broker.

- **Choose an LLM provider** (DeepSeek, Anthropic, OpenAI, Groq, OpenRouter) with your own key: `X-LLM-Provider` / `X-LLM-Model` headers, `GET /providers`, a selector in the upload form. The base URL comes only from a server-side allow-list (`src/llm/providers.py`, narrowed with `VISHAP_ALLOWED_PROVIDERS`); a request can never supply a URL. A chosen provider always requires the caller's key, so the operator's key is never sent to another provider.

### Security
- **`/llm/config` required no authentication** and let anyone rewrite the server's LLM URL/model/key (the operator's key could be redirected to any host). The router now needs the API key; with `VISHAP_REQUIRE_USER_LLM_KEY=1` (or `VISHAP_LLM_CONFIG_LOCKED=1`) `POST /llm/config` answers 403 and `GET` returns `locked: true`. `custom_url` must be http(s).

### Changed
- The "LLM Provider" panel: on a locked server it stores the visitor's own provider / model / key in the browser (shared with the upload form); on a local/desktop install it still edits the backend settings, now through the authenticated client. Heading was white-on-white; the Anthropic preset uses `claude-sonnet-5-5`.

### UI
- **Readable pages**: `/analyze`, the report page, the upload form and job cards used a dark-theme palette (`text-slate-100`, `bg-slate-900/60`, ...) on the light page, so headings, labels and fields were nearly invisible. Moved to the light palette used by the rest of the app; markdown blockquotes got readable colours too.
- **"Try example (SQLi)"** links to `/analyze?example=sqli`, but nothing read the parameter; the form is now prefilled.
- Footer shows the real version (it was hard-coded `7.3.16`; now read from `package.json`).
- LLM settings moved out of the "Recent analyses" list into their own section; removed an empty block.

### Fixed
- `/analyze/async` (what the UI calls) ignored `X-LLM-Api-Key`; the key also did not reach worker threads (`run_in_executor`, batch pool). CORS did not allow the `X-LLM-Api-Key` header. `ui-next/src/lib/api.ts` only sent it when `NEXT_PUBLIC_API_KEY` was set; the upload form had no key field.

### CI
- `pip-audit` (informational) and `pytest --cov=src` coverage report.

### Tests
- `tests/test_security_hardening.py`.

## [7.4.6] - 2026-10-26

### Added
- **Claude plugin `vishap-security-bundle`** (`claude-plugin-bundle-anthropic/`): `vishap_analyze` tool with `title`, `readOnlyHint`, `destructiveHint`, `openWorldHint`; README with Privacy section; `requirements.txt`.
- Root `.claude-plugin/marketplace.json` — `/plugin marketplace add dvddv9/vishap`, `/plugin install vishap-security-bundle@vishap`.
- `tests/test_plugin_bundle_key_safety.py` — guard: the plugin never uses the publisher's API key.
- `dsh-plugin/` — DeepSeek Harness tool ships with the repo.

### Changed
- Plugin reads only plugin-scoped `VISHAP_API_KEY` / `VISHAP_MODEL` (from user settings); no ambient credentials.
- Plugin input limit 200 KB; analysed material wrapped in a unique data delimiter; warning when the model output is truncated at `max_tokens`.
- Versions synced to 7.4.6 (`src/version.py`, `pyproject.toml`, `ui-next`, README badge).
- README: "What's new" and LLM backend description match the code (OpenAI-compatible endpoint via `CUSTOM_LLM_URL`).

### Fixed
- `/analyze`: a stage returning `None` no longer raises `AttributeError` (HTTP 500); defaults for `filename` / `timestamp` restored.
- CI: stale Stripe tests removed, Docker smoke-test env, UTF-8 BOM stripped from `src`.

### Removed
- Scratch scripts (`_test_*.py`, `fix-plugin.py`, `patch-logs.py`) are no longer tracked.

## [7.4.0 – 7.4.4] - 2026-10-26 … 2026-10-26

Summary (see the git tags v7.4.0 … v7.4.4 for details):
- **7.4.0** — logs as material (`LOG_PATTERNS`, `scan_log`), drift fixes (CWE-359 / GDPR Art. 32), SECURITY.md update.
- **7.4.1** — `detect_language` extension-order fix, `run_tests` sync.
- **7.4.2** — `/version` endpoint, fail-closed startup (`CONVEYOR_API_KEY`), `hmac.compare_digest`, `uuid4` session ids.
- **7.4.3** — default host `127.0.0.1` (override with `VISHAP_HOST`), version sync.
- **7.4.4** — D0 fast path (empty / trivial / unparseable material skips the LLM).

## [7.3.16] - 2026-10-24

### Added
- **Provider selection restored** — `VISHAP_LLM_PROVIDER` (custom | openai | groq | ollama | dsh | auto). Default: `custom` (DeepSeek API).
- `.env.example`: provider examples (DeepSeek / OpenAI / Groq / Ollama / DSH).
- `LLMSettings.tsx`: provider dropdown (custom / openai / groq / ollama / dsh).

### Fixed
- `_resolve_provider()` — env-based selection (custom default).
- `storage/mode.py`: `VALID_MODES = (custom, dsh, openai, groq, ollama)`.
- `.env.example`: deduplicated (one provider block).
- `LLMSettings.tsx`: HTML comment removed (JSX parse fix).

## [7.3.15] - 2026-10-24

### Added
- **Fix-loop** (`VISHAP_FIXER=1`) — stage4.5: «Apply fix, run ruff + pytest + mypy in sandbox». Result: accepted / rejected.
  - Verified: on XSS — fix accepted 3/3 (`ruff: All checks passed!`).
- **Sandbox** (`apply_fix_and_verify`) — ruff + pytest + mypy (optional), 10s timeout, isolated temp dir.
- `result_sess-*.json`: now saves `stage4_5` (debug/audit).

### Changed
- `stage4_5_fixer`: max 3 fixes, strip markdown fences, RCE risk (use VISHAP_FIXER=1 only for trusted material).

## [7.3.14] - 2026-10-23

### Added
- **Test-first loop** (`VISHAP_TESTER=1`) — stage3.5: «Write pytest that reproduces the defect, run in sandbox». Result: confirmed / false_positive (merged into stage4).
  - Verified: on SQLi — generated test passed in sandbox, CWE-89 confirmed.
  - Verified: on XSS — test failed (false positive, weak test).
- **Sandbox** (`src/pipeline/sandbox.py`) — 5s timeout, no network (best-effort), isolated temp dir.
- `result_sess-*.json`: now saves `stage3_5` (debug/audit).

### Changed
- `stage3_5_tester`: max 3 tests, strip markdown fences, RCE risk (use VISHAP_TESTER=1 only for trusted material).

## [7.3.13] - 2026-10-23

### Added
- **Cross-language translator** (`VISHAP_TRANSLATOR=1`) — stage1.5: «Here is SQLi in Python. How does it look in Java / C / Go?» Result merged into stage2 context (only if stage1.findings non-empty).
- `result_sess-*.json`: now saves `stage1_5` and `stage2_5` (debug/audit).

### Changed
- `stage1_5_translator`: max 10 findings, truncate to 4000 chars, async_mode support, JSON parse fallback.
- **Note:** translator works only for SAST findings (SQLi, path traversal, hardcoded secret). XSS (LLM-only) is not translated.

## [7.3.12] - 2026-10-23

### Changed
- **Default provider: DeepSeek API** (`https://api.deepseek.com/v1`, `deepseek-chat`). DSH endpoint is now **optional**.
- `.env.example`: `CUSTOM_LLM_URL=https://api.deepseek.com/v1` + comment.
- README: DSH section marked as optional.
- `_resolve_provider()`: docstring updated.

## [7.3.11] - 2026-10-23

### Added
- **Self-adversarial red team** (`VISHAP_REDTEAM=1`) — one DeepSeek, second pass: «You are red team. Find what Analyst missed.» Result merged into stage4 context.
- **Runbook in Transmitter** — `stage5_transmitter` prompt extended (runbook: how to fix + verify).
- `prompts/` — **not present** (prompts are inline in `stages.py`).

### Changed
- `stage2_5_redteam` runs **only** if `VISHAP_REDTEAM=1` (default off — no extra cost).

## [7.3.10] - 2026-10-23

### Changed
- **UI: light theme** — `globals.css` switched from dark (`#070b10`) to light (`#f8fafc` / `#0f172a`). Hero, FeatureGrid, EmptyState, Navbar, footer, JobCard, LLMSettings — all light.
- `layout.tsx`: `VISHAP_VERSION` synced to `7.3.10`.

## [7.3.9] - 2026-10-23

### Added
- **UI: beautiful hero** — gradient background, animated CTA, «Why Vishap?» bullets (`components/Hero.tsx`).
- **UI: feature grid** — 3 cards (SAST / pipeline / SARIF) (`components/FeatureGrid.tsx`).

### Changed
- `page.tsx`: inline hero replaced with `<Hero />` + `<FeatureGrid />`.

## [7.3.8] - 2026-10-23

### Added
- **UI: empty state CTA** — `ui-next/src/components/EmptyState.tsx` («Analyze code →» + «Try example (SQLi)») instead of passive «No analyses yet» text.

## [7.3.7] - 2026-10-23

### Added
- **README: DSH endpoint section** — install `dsh-model-endpoint`, enable in DSH (Settings → Model endpoint), configure Vishap, and verify.
- Clarified: `CUSTOM_LLM_MODEL=auto` means "use the model selected in DSH".

## [7.3.6] - 2026-10-23

### Removed
- **UI cleanup:** removed `ui-next/src/components/HarnessBadge.tsx`, `getHarnessStatus()` / `startHarness()` from `api.ts`, `HarnessStatus` interface from `types.ts`, `harness` option from `LLMSettings.tsx`.

### Changed
- `LLMSettings`: provider is `custom` only (no `harness` option).

## [7.3.5] - 2026-10-23

### Removed
- **Legacy `harness` provider removed.** Vishap is now endpoint-only: `VISHAP_LLM_PROVIDER=custom` + `CUSTOM_LLM_URL` (OpenAI-compatible, e.g. DSH endpoint `http://127.0.0.1:8787/v1` via `dsh-model-endpoint`).
- Removed `src/llm/harness_client.py`, `src/llm/harness_launcher.py`, `HARNESS_*` env vars, `/harness/*` endpoints.
- Removed `tests/test_harness_api.py`, `tests/test_harness_launcher.py`.

### Changed
- `_resolve_provider()` always returns `"custom"`.
- `src/storage/mode.py`: `VALID_MODES = ("custom",)`.
- `.env.example`: only `CUSTOM_LLM_*` + `VISHAP_LLM_PROVIDER=custom`.

### Migration
If you used `HARNESS_*`, switch to `dsh-model-endpoint`:
```
VISHAP_LLM_PROVIDER=custom
CUSTOM_LLM_URL=http://127.0.0.1:8787/v1
CUSTOM_LLM_KEY=<dsh-key>
CUSTOM_LLM_MODEL=auto
```

## [7.3.4] - 2026-10-23

### Fixed
- `custom_client.py`: fallback to `message.reasoning_content` when `content` is empty (DeepSeek flash / V4 reasoning models).
- `stages.py::parse_json_response`: recover JSON truncated at `max_tokens` (close unclosed `{`/`[`, cut at last valid object).
- Version sync: `src/version.py` as single source of truth; CI check via `scripts/check_version.py`.

### Changed
- **Default provider switched to `custom`** (OpenAI-compatible endpoint). For local DSH: set `CUSTOM_LLM_URL=http://127.0.0.1:8787/v1` + `CUSTOM_LLM_KEY=<dsh-key>`. `harness` remains as fallback (set `VISHAP_LLM_PROVIDER=harness`).

### Added
- DSH endpoint support via `dsh-model-endpoint` plugin (`http://127.0.0.1:8787/v1`, OpenAI-compatible).

## [6.0.1] - 2026-10-15

### Added

- **UI: async analysis, LLM mode sidebar, dataflow rendering.**
  - Custom header (рџђ‰ gradient) + CSS theme.
  - Sidebar: LLM mode selector (`auto` / `cloud` / `local`).
  - `вљЎ Async` button -- non-blocking analysis via async API.
  - Dataflow expander -- shows `dataflow_path` for Java/C.

### Tests

- `tests/test_ui_async.py` (new) -- 19 tests.
- 435 passing (was 416).

## [6.0.0] - 2026-10-15

### Added

- **Async API -- job-based analysis.**
  - `src/api/jobs.py` (new) -- in-memory job store, thread-safe.
  - `POST /analyze/async` -- returns `{job_id, status: "queued"}` immediately.
  - `GET /status/{job_id}` -- poll job status.
  - `GET /report/{job_id}` -- fetch result (409 if not done).
  - `BackgroundTasks` -- pipeline runs in background.
  - Sync `/analyze` unchanged (backward compatible).

### Tests

- `tests/test_async_api.py` (new) -- 20 tests.
- 416 passing (was 396).

### Dogfood

- Full end-to-end: POST -> job_id -> poll (42s) -> report with stages 0-4 + audit.

## [5.11.6] - 2026-10-15

### Added

- **P2-7: C taint patterns (regex-based data flow).**
  - `TAINT_SOURCES["source_c"]` -- scanf/fgets/gets/read/recv, argv[], getenv.
  - `TAINT_SINKS["sink_c_cmd|buffer|file"]` -- cmd, buffer, file.
  - `EXPLOIT_PATTERNS["entrypoint_c_main|jni"]`, `blast_c_cmd|buffer|file`.
  - `_LANG_ENTRYPOINTS["c"]` -- C entry points mapping.
  - `trace_taint` auto-detects C.
  - Blast radius logic extended for C: `c_cmd` -> high, `c_buffer` -> medium, `c_file` -> low.

### Tests

- `tests/test_patterns_c.py` (new) -- 35 tests.
- 396 passing (was 361).

### Dogfood

- `examples/own/c_cmd_injection.c` (new) -- path `main -> argv[1] -> strcpy -> system`, blast_radius: high.

## [5.11.5] - 2026-10-15

### Added

- **P2-7: Java taint patterns (regex-based data flow).**
  - `TAINT_SOURCES["source_java"]` -- Servlet/Spring/System/IO sources.
  - `TAINT_SINKS["sink_java_sql|cmd|file|reflect|deser|jndi"]` -- SQL, cmd, file, reflection, deserialization, JNDI (Log4Shell).
  - `EXPLOIT_PATTERNS["entrypoint_java_main|spring|servlet"]` -- main, Spring annotations, Servlet doGet/doPost.
  - `_LANG_ENTRYPOINTS["java"]` -- entry points mapping.
  - `trace_taint` auto-detects Java; comment lines skipped.

### Tests

- `tests/test_patterns_java.py` (new) -- 41 tests.
- 361 passing (was 320).

### Dogfood

- `examples/own/ServletSqli.java` (new) -- path `doGet -> getParameter -> createStatement`.
- Known limitation: `DbConnection.java` path is empty (source via method argument, no AST for Java).

## [5.11.3] - 2026-10-15

### Changed

- **Refactor: UI api_client.py** -- `streamlit_app.py` had 8 duplicated `requests.*` calls with manual `headers=HEADERS`. Headers defined in 3 places.
  - New module: `src/ui/api_client.py` -- `get()`, `post()`, `_url()` with auto headers + timeouts.
  - `src/config.py`: added `API_URL`, `CONVEYOR_API_KEY`, `API_TIMEOUT_*`.
  - `src/ui/streamlit_app.py`: 8 calls refactored, local `API_URL`/`API_KEY`/`HEADERS` removed.

### Added

- `tests/test_api_client.py` -- 16 tests (mocked HTTP).
- `tests/test_ui_headers.py` -- rewritten: 13 tests (now checks `api_client` and absence of direct `requests.*` in UI).

### Tests

- 320 passing (was 297).

## [5.11.2] - 2026-10-15

### Changed

- **Refactor: consolidated risk verdict computation** -- `run_audit()` had ~45 lines of inline verdict logic (v5.10.6 + v5.11.1) with duplicated `critique` / `risk_verdict` branches.
  - New module: `src/pipeline/verdict.py`.
  - Function: `compute_risk_verdict(stage2_result, pii, compliance, cwe_ids, force_emergency) -> (risk_verdict, critique_verdict)`.
  - Priority order: emergency > pii/compliance/cwe > critical risk_nodes > critical security.findings > SAFE.

### Fixed

- `critique_verdict` now correctly returns `EMERGENCY` on force_emergency (was `SAFE` -- inconsistent with `risk_verdict`).

### Added

- `tests/test_verdict.py` -- 26 tests.

### Tests

- 297 passing (was 271).

## [5.11.1] - 2026-10-15

### Fixed

- **risk_verdict ignored stage2.security.findings** -- `run_audit()` only checked `stage2.risk_nodes` (v5.10.6), ignoring `stage2.security.findings`. A file with critical `SEC-N` but no critical `RN-N` got a false `SAFE`. Fix: scan both `risk_nodes` and `security.findings` for critical priority.

### Added

- `tests/test_risk_verdict_security.py` -- 8 regression tests.

### Tests

- 271 passing (was 263).

## [5.7.1] - 2026-10-12

### Fixed (review + dogfood P0)

- **material_hash collisions** вЂ” context (filename + session_id) added to hash input (`ce3953d`)
- **PII redaction before LLM** вЂ” 15 regex patterns, placeholders (`<EMAIL_REDACTED>`) before cloud send (`7b23c24`)
- **LLM HTTP timeout** вЂ” 60s + tenacity retry with exponential backoff (`9063927`)
- **API auth + rate limit** вЂ” X-API-Key + 10/min limiter + CORS + 127.0.0.1 fallback (`fbfb48f`)
- **EMERGENCY-downgrade gate** вЂ” CRITICAL_RISK_PATTERNS (RCE, SQLi, path traversal, XXE, SSTI, LDAPi) (`48dddd0`)
- **[AUDIT_TRAIL] dedup** вЂ” strip_llm_audit_blocks from LLM output (`2000501`)
- **material_hash_full** вЂ” SHA-256 of original (before truncation) (`8ca7f4e`)
- **material_complete** вЂ” deterministic `not truncated` (`9459a53`)
- **risk_verdict** вЂ” separated from critique_verdict (`e500c80`)
- **emergency path UnboundLocalError** вЂ” fixed (`e500c80`)
- **748 material_hash places** вЂ” all 64-hex or LEGACY (`71af15f`, `0e68b05`, `08ce35d`)

### Added

- **PROOF.md** вЂ” 13 evidence sections (`e6d3829`, `0e68b05`)
- **FINDINGS.md** вЂ” dogfood findings, 5 P0 bugs (`a5b444f`)
- **8 dogfood reports** вЂ” code, config, spec, data (`27aabb4`)
- **STONESOUP CWE-129B** вЂ” SARD case study (`a48b228`)
- **deployment/** вЂ” Dockerfile, docker-compose, systemd, .env.example (`003f9a8`)
- **SECURITY.md** вЂ” threat model + controls + honest boundaries (`7929f1e`)
- **docs/LIMITATIONS.md** вЂ” 10 honest boundaries (`ce7cf19`)
- **docs/FAQ.md** вЂ” 10 common questions (`acba0af`)
- **src/api/auth.py** вЂ” X-API-Key dependency
- **src/api/rate_limit.py** вЂ” in-memory sliding window
- **src/tools/redact.py** вЂ” pre-LLM redaction
- **src/tools/patterns.py** вЂ” PII_PATTERNS + CRITICAL_RISK_PATTERNS

### Changed

- `compute_hash` вЂ” added `context` param
- `run_audit` вЂ” added `force_emergency`, `context`, `redaction_map` params
- `AnalyzeResponse` вЂ” added `audit`, `completeness`, `material_hash_full`, `truncated`, `original_size`
- `run_pipeline` вЂ” redaction before Stage 0
- `uvicorn.run` вЂ” dynamic host (127.0.0.1 if no API key)

### Security

- API key from `VISHAP_API_KEY` env var
- CORS restricted to `localhost:8501`
- Rate limit 10/min for /analyze
- PII/secrets redacted before cloud LLM

---

## [5.7.0] - 2026-10-08

### Added

- **6-stage LLM pipeline** вЂ” Orchestrator, Scanner, Analyst, Researcher, Synthesizer, Transmitter
- **Multi-material** вЂ” code (.py, .go, .js, .ts, .java, .rs), spec (.md), logs (.txt), config (.yaml, .json), data (.json)
- **Audit trail** вЂ” SHA-256 material_hash, pii_detected, compliance_flags, critique_verdict
- **EMERGENCY interrupt** вЂ” Stage 0 stops pipeline on critical risk
- **FastAPI API** вЂ” /analyze, /analyze/batch, /history, /mode, /health
- **Streamlit UI** вЂ” file upload, history, download markdown
- **DeepSeek cloud** + **Ollama local** fallback
- **41 tests** вЂ” PII, compliance, JSON, pipeline mock, e2e
- **39 case studies** вЂ” FastAPI, Django, Flask, Express, Go stdlib, Log4Shell, OpenSSL, Redis, K8s, PostgreSQL, Juice Shop, DVGA, RailsGoat, DVWA, TerraGoat
- **CI** вЂ” GitHub Actions, py3.11 + py3.12

### Known limitations

- Truncation at 12 000 chars
- LLM-based (may produce false positives)
- No SAST/SCA integration
- No SARIF output
- No formal threat model (added in 5.7.1)

---

[5.7.1]: https://github.com/dvddv9/vishap/compare/v5.7.0...v5.7.1
[5.7.0]: https://github.com/dvddv9/vishap/releases/tag/v5.7.0

*Vishap V5.8 - production-ready.*
