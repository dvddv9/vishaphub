# Workflows

- `ci.yml`: on push and pull request to `main`: version check, ruff (F and E9), the full test suite on Python 3.11 and 3.12.
  The tests use a stub instead of the model: no key, no network.

The repository is local for now (no remote), so these run only once it is pushed somewhere.
