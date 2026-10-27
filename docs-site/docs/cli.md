# CLI

The `vishap` entry point (defined in `pyproject.toml` → `src.cli:main`) wraps the pipeline and the deterministic tools.

## `vishap analyze`

```bash
vishap analyze <file> [--gate] [--sarif out.sarif] [--sbom out.json] [--diff REF] [--context-root DIR]
```

| Flag | Meaning |
|---|---|
| `--gate` | quality gate: exit 1 when the verdict is REQUIRES_REVIEW, 0 when SAFE |
| `--sarif <out>` | write SARIF 2.1.0 (GitHub Code Scanning) |
| `--sbom <out>` | write a CycloneDX SBOM |
| `--diff <ref>` | analyze only files changed vs. ref |
| `--context-root <dir>` | pull in related files (inter-file analysis) |

Exit codes

Code Meaning
0 pass
1 gate failed
2 internal error
3 skipped (file unchanged + --gate)

Example

```bash
vishap analyze src/app.py --gate --sarif out.sarif
```

---

vishap sbom

```bash
vishap sbom --output sbom.json
```

Generates a CycloneDX SBOM from installed dependencies.

---

Deterministic tools

The CLI also exposes the analyzer used by Stage 2:

```bash
python src/tools/analyze.py --mode security --input file.py
python src/tools/analyze.py --mode contracts --input file.py
python src/tools/analyze.py --mode concurrency --input file.py
```

Modes: static, security, metrics, deps, tests, calc, cost, migrate, concurrency, contracts.

---

LLM providers

Vishap talks to any OpenAI-compatible endpoint. Set it in `.env` (or via the UI):

Variable Notes
CUSTOM_LLM_URL Endpoint base URL (Claude: https://api.anthropic.com/v1)
CUSTOM_LLM_KEY API key
CUSTOM_LLM_MODEL Model name (Claude: claude-sonnet-5-5)
CUSTOM_LLM_SEND_TEMPERATURE Set to false for Claude 5.x

```env
CUSTOM_LLM_URL=https://api.anthropic.com/v1
CUSTOM_LLM_KEY=sk-ant-...
CUSTOM_LLM_MODEL=claude-sonnet-5-5
CUSTOM_LLM_SEND_TEMPERATURE=false
```

---

Local scripts (Windows)

Script What it does
install.bat Installs Python, Node.js, PostgreSQL, and dependencies
apply_custom_llm.py Adds the OpenAI-compatible provider to an existing checkout

```
