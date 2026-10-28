# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project

vishap-generator (v0.4.0): a spec-to-code generator that proves its output. `spec.yaml` goes in; files, tests and
a trace "requirement -> code -> test -> finding" come out. Five stages: Intake, Design, Build, Verify, Deliver.
A requirement is `passed`, `failed`, `needs_verification` or `not_verified`; "not proven" is never reported as "passed".

- Stack: Python 3.11+, standard library plus PyYAML. Optional: `coverage`, `ruff`. No web framework: the server is `http.server`.
- The model is any OpenAI-compatible endpoint, configured only from the environment (`CUSTOM_LLM_*`).
- It is a separate project from Vishap. The Vishap analyzer is called as an external program (`vishap analyze`).
- The repository is local: no remote, never push.

## Commands

    python run_tests.py                       # all tests, no network, no model
    python run_tests.py --lint                # plus ruff and the version check
    python -m unittest tests.test_verify      # one module
    python -m generator serve                 # web form and API on http://127.0.0.1:8787/
    python -m generator generate examples/spec-clean.yaml --out out/ --gate

Without `pip install -e .`, set `$env:PYTHONPATH = "src"` first.

## Layout

    src/generator/
      version.py config.py cli.py main.py     version, settings, command line, HTTP server
      api/        auth, errors, rate_limit, llm_config, reports, jobs   (what main.py needs)
      llm/        providers.py (settings), client.py (one chat call), _scrub.py (keys out of text)
      pipeline/   intake design build generate verify deliver textcheck, orchestrator, stages,
                  prompts (loader), sandbox + _sandbox_runner (child process)
      tools/      spec gaps analyzer sarif examples
      prompts/    00_rules 02_design_textcheck 03_build 03_build_repair (.md) - see prompts/README.md
      web/        index.html (single-file SPA)

## Rules that must keep holding

- Every prompt is a file in `prompts/`; no prompt text inside Python. A new prompt is listed in
  `pipeline/stages.py`; `tests/test_prompts.py` fails otherwise.
- Data from the user or from tools reaches the model only through `wrap_data()` (random markers).
- The gate (`deliver.gate_check`) blocks on: build errors, critical/high requirement not `passed`, analyzer failed,
  coverage under 80%, open critical gap, spec older than 90 days, Verify problems. Do not weaken it to make a test pass.
- Verify's sandbox is a child process, not isolation. Never describe it as safe against hostile code.
- The API never writes to the server's disk and never stores or logs model keys.
- Secrets: the key lives only in environment variables of the session. Never put one in a file, a commit, a log or a test.
- Tests use stubs for the model (see `tests/test_pipeline.py: Stub`); no test calls the network.

## Commits

Local only. Identity: `git -c user.name="David" -c user.email="hndav9@yahoo.com" commit ...`.
Keep the Co-Authored-By and Claude-Session trailers the harness asks for.
