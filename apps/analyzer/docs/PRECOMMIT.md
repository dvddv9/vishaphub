# Pre-commit

## Install

    pip install pre-commit
    pre-commit install

Now every git commit runs:

- **gitleaks** - secret scanning
- **check-yaml**, **check-json**, **detect-private-key**
- **ruff** - Python lint
- **bandit** - Python security

## Run manually

    pre-commit run --all-files

## Skip (emergency only)

    git commit --no-verify -m "..."

Use only when you are sure. Bypassing secret scanning is dangerous.

## CI integration

Add to .github/workflows/tests.yml:

    - uses: pre-commit/action@v3.0.1

## Files

- .pre-commit-config.yaml - hook definitions
- .gitleaks.toml - gitleaks config (allowlist)

## Allowlist

.gitleaks.toml allowlists:

- tests/ - fake secrets in tests
- docs/case-studies/ - redacted examples
- examples/ - fake data
- src/tools/patterns.py - the detector itself
- src/tools/redact.py - the redactor itself

Placeholders (<EMAIL_REDACTED>, sk-your-key-here) are allowlisted.
