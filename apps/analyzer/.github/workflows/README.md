# GitHub Actions workflows

- **`ci.yml`** -- main CI: `ruff check src/` (F + E9) + `pytest tests/ --ignore=tests/test_e2e.py`,
  Python 3.11/3.12 matrix, Postgres 16 service (integration tests run if `TEST_POSTGRES_URL` is set).
- **`vishap.yml`** -- dogfood: Vishap scan on changed files (SARIF upload + quality gate + SBOM).
- **`tests.yml`** -- legacy: `python run_tests.py`. Superseded by `ci.yml`; can be removed later.

## Run locally

```powershell
.\.venv\Scripts\Activate.ps1
pip install ruff pytest-asyncio
ruff check src/ --select F,E9
python -m pytest tests/ --ignore=tests/test_e2e.py -q
```

## Add a new job

Add a `jobs.<name>:` block to `ci.yml` (or a new file in `.github/workflows/`).
Use `runs-on: ubuntu-latest`, `actions/checkout@v4`, `actions/setup-python@v5`.
Set `timeout-minutes` (15 for test jobs) and pin action versions.

## Notes

- Integration tests need Postgres: `TEST_POSTGRES_URL` (see `tests/test_job_store_postgres_integration.py`).
- E2E tests (`tests/test_e2e.py`) are excluded -- they call a real LLM.
- `VISHAP_DATA_DIR` points into the GitHub workspace so tests can write result/audit files.
