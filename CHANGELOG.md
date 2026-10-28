# Changelog

All notable changes to vishap-generator. Format based on [Keep a Changelog](https://keepachangelog.com/).

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
