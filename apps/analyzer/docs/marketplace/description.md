# GitHub Marketplace listing — Vishap

Working copy of the fields to paste into the Marketplace listing form.
No marketing superlatives: every claim below is something the product does.

## Short description (≤140 chars)

```
Automated security analysis for engineering materials (Python, Java, C).
```

75 characters.

## Categories

1. **Security**
2. **Code review**
3. **CI / CD**

## Long description

Vishap reviews code, configuration, specifications, logs and structured data and
returns a structured Markdown report: risks ranked by severity, a STRIDE threat
model, refactoring options with effort estimates, and an audit trail.

**How it works.** Six pipeline stages read the material, run deterministic SAST
and SCA tooling alongside an LLM pass, and synthesise one report. Deterministic
findings and model findings are kept separate, so you can see which is which.
Every report carries a SHA-256 hash of the analysed slice and the provenance
commit, so a finding can be traced back to an exact revision.

**What you get per analysis.**

- Findings mapped to CWE and OWASP Top 10, with severity and the function or
  file they point at.
- A STRIDE threat model built from those findings, not from a generic checklist.
- Refactoring options with effort estimates (days, not story points).
- SARIF 2.1.0 and CycloneDX SBOM output for your existing security tooling.
- An audit trail: material hash, commit, CWE list, PII-redaction flags,
  anomaly detection over line lengths.

**Where it fits.**

- **Pull requests** — the GitHub App analyses a PR diff and comments with the
  report, so the review happens where the code is.
- **Release gates** — the CLI exits non-zero when a quality gate fails, which
  makes it usable as a CI step without parsing output.
- **Compliance preparation** — audit export (CSV/JSON), per-tenant isolation and
  a documented retention policy for SOC 2 / ISO 27001 evidence collection.
- **Legacy code triage** — point it at a file you inherited and get a ranked
  list of what to look at first.

**What it is not.** Vishap is not a proof-of-concept generator and does not
claim exploitability. Findings are triage candidates: the report says
`REQUIRES_REVIEW` when it sees enough signal to warrant a human look, and
`SAFE` only when it does not. It complements SAST and fuzzing rather than
replacing them.

**Supported material.** Python, Java, C, JavaScript/TypeScript, Go, Ruby, PHP,
YAML, Terraform, Markdown, and plain logs or specs. Analysis runs on the
material you paste or upload; PII is redacted before it reaches a model.

## Links

| Field | Value |
| --- | --- |
| Homepage | https://dvddv9.github.io/vishap/ |
| Documentation | https://dvddv9.github.io/vishap/docs/getting-started |
| Support | support@vishap.dev |
| Privacy policy | https://dvddv9.github.io/vishap/docs/legal/privacy |
| Terms of service | https://dvddv9.github.io/vishap/docs/legal/terms |
| License | AGPL-3.0 |

## Screenshots

See [`screenshots/`](screenshots/) — three placeholders describing the shots to
capture (`1280×800`, PNG, no customer data, no browser chrome).
