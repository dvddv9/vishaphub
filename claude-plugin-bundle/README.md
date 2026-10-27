# Vishap Security Analysis

Analyze engineering materials (code, spec, logs, config, data) for security risks using Anthropic Claude.

This skill teaches Claude to:

- Detect SQLi, XSS, RCE, TOCTOU, path traversal, command injection, auth bypass.
- Produce a structured Markdown report: summary, critical risks (with CWE), recommended fixes, STRIDE threat model.
- Cite line numbers and exploitability. State assumptions when uncertain.

## Usage

In Claude, ask:

> "Analyze this Python snippet for SQL injection: `db.execute(f\"SELECT * FROM users WHERE name = '{name}'\")`"

or

> "Run a security review of my Dockerfile: [paste]"

Claude will analyze the material and return a structured Markdown report.

## License

AGPL-3.0-or-later — see [LICENSE](LICENSE).
