# Changelog

All notable changes to vishap-generator. Format based on [Keep a Changelog](https://keepachangelog.com/).

## [0.7.0] - 2026-10-28

### Added
- Verify's attacks and the COVE probes reach inputs in `body` and `path`, not only `query` and `header`. `body`: one JSON object with `Content-Type: application/json`, the attacked field carries the value and the other fields valid ones. `path`: the value replaces the placeholder of the route (`<name>`, `<int:name>`, `{name}`); a path input whose route has no placeholder is skipped with the reason; a path value is never "absent" or "empty" (that is another route). The trailing-newline attack (the `$` bug) now runs for `query`, `body` and `path`.
- Two examples for the form: "Create user (JSON body)" and "Item by path". The build prompt tells the model how Verify sends each kind of input.
- `verify.make_request`, `default_values`, `route_has` (shared by Verify and COVE).

### Not verified
No real model was run: the attacks were checked against hand-written apps.

## [0.6.1] - 2026-10-28

### Added
- `GENERATOR_CHECK_ONLY=1`: a public demo mode. The server answers only `/api/check` (no model, no code run), refuses `/api/generate*` with 403, ignores client model settings and may listen on a public address without a token. Names it answers to: `RENDER_EXTERNAL_HOSTNAME`, `GENERATOR_PUBLIC_HOSTS`. `/api/status` has `check_only`; the web form hides the run controls and the model settings and says so.
- `render.yaml`: a Render blueprint for that demo (docker, free plan, port 8787). `deploy/README.md` explains it.

### Changed
- In the demo the run page says "Edit the spec and check again".

### Verified
Deployed on Render (docker, free plan): `/api/status` shows `check_only`, the page and the STRIDE table work.

## [0.6.0] - 2026-10-28

Checks taken from a review of the "meta-prompt" ideas (STRIDE, STRICT, COVE, self-refine, USC, Reflexion, audit trail).
Each one was changed to fit a tool that has a way to run code: where the idea was a model opinion, here it is either
read from the spec (deterministic) or judged by running the code. The command line, the API and the prompts of 0.5.0
are compatible; new keys and flags were added, none removed.

### Added (no extra model call)
- **STRIDE table** (`tools/stride.py`): for each of the six threats, whether the spec has a requirement for it
  (`covered`, `partial`, `not_covered`, `not_applicable`). It reads the spec, never the code. After Verify each row
  gets `proof`: proven / failed / not proven. Not a gap by default; gate key `require_stride: [T, I]` blocks.
- **STRICT** (`--strict`, or gate key `strict_missing_pct`): refuses a spec that lacks more than the given share of
  the key data and says which parts are missing (`spec: Cannot answer reliably. Missing: ...`, exit 2, HTTP 422).
- **Injection scan** (`tools/injection.py`): phrases aimed at the model are a critical gap `injection`;
  `INJECTION_STOP` (3) or more stop the run.
- **Secret in the spec** is now a critical gap `secret` (kinds and counts, never values).
- **Domain reminders** (`domain:` in a spec, `tools/domains.py`): noted gaps of type `reminder`, never blocking.
- **Incomplete output**: `loss_pct` (share of planned code and test files the model left out); over
  `max_loss_pct` (default 30) it is a problem.
- **Effort**: `--effort quick|standard|deep` sets repairs, candidates, text check, Analyzer and COVE together; a flag
  given on its own wins. `--repro` asks for temperature 0 and a fixed seed (refused together with several candidates).
- Audit extras in the trace: `provenance.pii_detected`, `usage.tokens_reported`, `model.repro`, and `effort`,
  `threats`, `loss_pct`, `candidates`, `cove`, `repair_stopped` (no times, so the trace stays repeatable).
- Gate keys: `strict_missing_pct`, `require_stride`, `fail_on_cove`, `max_loss_pct`.

### Added (extra model calls, judged by running the code)
- **Candidates** (`--candidates N`, 1 to 5; `pipeline/candidates.py`): N answers of the model, each built and verified;
  the one with the most proof wins, ties go to the lowest number. Costs N times the Build tokens.
- **Round memory**: the repair prompt carries the problems of the earlier rounds; the same problems twice in a row
  stop the loop early (`repair stopped early` in the notes) instead of spending the remaining rounds.
- **COVE** (`--cove`, `pipeline/cove.py`, prompt `04_verify_cove`): the model answers from the spec alone what the
  service should do on unusual values (a letter outside A-Z, `\u0663`, underscore, a leading space); the sandbox runs
  the code on the same values; differences are notes, and a gate reason only with `fail_on_cove`. "unclear" is never
  a mismatch.

### Changed
- `repairs` and `text_check` default to the effort (standard: 2 and on); the API takes `effort`, `candidates`, `cove`,
  `strict` (a bad value is 400). The web form has the same controls and shows the STRIDE table, the candidates and the
  COVE comparison; the report has the same sections.
- The model's `usage` counts calls made from several threads into the same run.

### Not verified
No real model was run: COVE, candidates and the prompts were exercised with a stub model. Docker and CI were not run.

## [0.5.0] - 2026-10-28

Every part of the generator now follows the Vishap component that does the same job (mapping table in `docs/ARCHITECTURE.md`).
The command line, the API and the JSON contract of the prompts are compatible with 0.4.1; new keys were added, none removed.

### Changed
- `pipeline/stages.py` is the registry of the five stages and holds `parse_json_response` (one place that reads a model's JSON answer) and `StageClock` (time and model use per stage, Vishap's `_meta`). The orchestrator records every stage; `PipelineResult` has `stages` and `usage`; `to_dict()` carries them.
- `pipeline/verdict.py` is the single place that turns evidence into a verdict (`apply_build_errors`); `tools/quality_gate.py` evaluates the gate from `.vishap-generator.yml` (`fail_on`, `coverage_min`, `stale_days`, `max_critical_gaps`, `fail_on_analyzer`, `require_coverage`, `baseline`); `tools/static_scan.py` holds the AST rules with CWE/OWASP ids.
- `llm/` is split like Vishap's: `custom_client.py` (the OpenAI-compatible call), `client.py` (`chat`), `_observe.py` (calls and tokens), `providers.py`, `_scrub.py`. The browser no longer sends a URL: it picks a provider id from the server's allow-list (`GET /api/providers`), so a request cannot make the server call an address of its choosing.
- Prompts: `wrap_material` (was `wrap_data`, still importable) and `build_prompt(name, material, context) -> (system, user)`.
- The web form starts a run as a job and shows the stage it is at and the log as it grows; the run page has a "Stages and model use" card and a Markdown report download.

### Added
- `tools/redact.py`: keys, tokens, private keys, JWTs, passwords in URLs and `password = ...` values are replaced by `[REDACTED:<kind>]` in everything that goes to the model; the text check matches quotes against the redacted text. Counts (never values) go into the trace.
- `tools/provenance.py`: the trace has a `provenance` block (generator version, spec hash, model name and host, prompt hashes, redaction counts).
- `pipeline/cost.py`: cost from `GENERATOR_PRICE_IN` / `GENERATOR_PRICE_OUT` (USD per 1M tokens); no price is invented, without them the cost is 0.0 and only token counts are shown.
- `storage/history.py`: `<out>/.vishap/history.json`, one entry per written run; a spec that already has a passed run with the same hash is skipped by `batch`.
- `observability/logging.py`: standard logging, `LOG_LEVEL`, `LOG_FORMAT=json|pretty`, run and request ids in every line, a filter that removes the model key. The server writes an access line (method, path, status, ms; never a body) and sends `X-Request-Id`.
- `pipeline/batch.py` and commands `batch`, `baseline`, `history`, `info`; `generate --report FILE` (Markdown); a usage line after `generate`.
- `tools/baseline.py`: `baseline spec.yaml` accepts the spec's current critical gaps on purpose; the gate lists them as accepted.
- API: `POST /api/generate/async` and `GET /api/jobs/<id>?since=N` (jobs in memory, 1 hour); a request limit per client address (`GENERATOR_RATE_LIMIT`, default 30 a minute, 0 = off) with `Retry-After`; `markdown`, `stages`, `usage`, `provenance` in the answer.
- `config.validate_config()` (shown by `info`), `.vishap-generator.yml.example`.

### Not taken from Vishap (does not apply to a local tool)
Tauri shell, Alembic, Postgres/Redis stores, accounts and billing, Celery, metrics and tracing exporters, Fernet storage of keys, SBOM/SCA, web search, landing and blog.

### Not checked
- No run against a real model in this session: the stage clock, token counts and prompts were exercised with a stand-in model server that returns fixed answers. Run `generate examples/spec-clean.yaml --out out/ --gate` once and compare with the earlier run (2 repair rounds).
- Docker files, CI, pre-commit and `.ps1`/`.bat` were not executed.

## [0.4.1] - 2026-10-28

### Changed
- The prompts are rewritten at the depth of Vishap's: sections Вход, Что делать, Самопроверка, Выход — JSON, Что запрещено, Тон, in Russian like Vishap's. `03_build.md` now tells the model exactly how Verify checks its answer (the rejected inputs Verify sends, `re.fullmatch` instead of `$`, no database and no network in tests, one route, the `sql-from-input` and `log-raw-input` rules, 80% coverage, the `# assumption:` marker). `03_build_repair.md` explains the problem lines of the repair round.
- The JSON contract of every prompt is unchanged, so the parsers did not change.

### Added
- Tests that keep the build prompt in step with Verify (coverage threshold, rejected input kinds, rule ids, test names) and check the section layout of each prompt.

### Not checked
- The new prompts were not run against a real model in this session (no key here); run `generate examples/spec-clean.yaml --out out/ --gate` once and compare with the earlier run (2 repair rounds).

## [0.4.0] - 2026-10-28

### Changed
- The code is laid out like Vishap: `api/`, `llm/`, `pipeline/`, `tools/`, `config.py`, `version.py`, `main.py` (was one flat folder). Import paths changed: `generator.pipeline.verify`, `generator.tools.spec`, `generator.pipeline.orchestrator.run_pipeline`, `generator.main.serve`.
- Every prompt is a file in `prompts/` (`00_rules`, `02_design_textcheck`, `03_build`, `03_build_repair`); `pipeline/stages.py` lists which stage uses which. `/api/status` returns the stages.
- Data goes to the model between random `VG_<LABEL>_<hex>` markers instead of fixed `<<<SPEC` / `SPEC>>>`: text inside a spec could close the fixed block and pass for instructions.
- The sandbox runner is its own module (`pipeline/sandbox.py`); settings and limits are in `config.py`.

### Added
- Project files like Vishap's: `LICENSE` (AGPL-3.0-or-later), `AGENTS.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `.dockerignore`, `ruff.toml`, `requirements*.txt`, `.pre-commit-config.yaml`, `.github/` (CI, issue and PR templates), `deploy/`, `run_tests.py`, `run_local.ps1`, `start_generator.bat`, `scripts/check_version.py`, and `docs/` (ARCHITECTURE, FAQ, LIMITATIONS, ROADMAP, VISHAP, HISTORY, stages).
- Tests for the prompt files and the layout.

## [0.3.0] - 2026-10-28

### Added
- Web form in the style of Vishap: dashboard, generate page, result page with eight tabs (Summary, Requirements, Files, Gaps, Analyzer, Diff, Audit, Full result), dark and light theme, phone layout.
- `/api/status`, `/api/examples`, model settings from the browser (`GENERATOR_ALLOW_CLIENT_LLM`), `diff` in the API answer.

### Fixed
- A build-check error no longer leaves the verdict at `passed`: it becomes `needs_verification` with a note, and the Summary shows a "Build check" card.

## [0.2.0] - 2026-10-28

### Added
- Line coverage always: built-in counter on `sys.settrace` when the `coverage` package is missing.
- `textcheck`: the model compares the free `text` of a spec with the requirements (report only, never blocks the gate).
- `init` command: a starting `spec.yaml` without open gaps.

## [0.1.1] - 2026-10-28

### Added
- `--require-coverage`: with `--gate`, coverage that could not be measured blocks writing.
- Optional dependencies `pip install -e .[full]` (coverage, ruff).

## [0.1.0] - 2026-10-28

### Added
- The five stages (Intake, Design, Build, Verify, Deliver), the gate, diff, backup, atomic write, trace and rollback.
- Verify with model tests, its own attacks, AST rules and the Vishap analyzer; up to N repair rounds.
- REST API, SARIF 2.1.0 output, OpenAI-compatible client with settings from the environment only.
