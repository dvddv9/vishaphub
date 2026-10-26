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

In v7.2.0, Vishap supports three LLM providers (set LLM_PROVIDER in .env or via the UI):

Provider Env variables Notes
deepseek DEEPSEEK_API_KEY Direct API calls to api.deepseek.com
harness HARNESS_URL, HARNESS_TOKEN Local DeepSeek Harness (DSH)
custom CUSTOM_LLM_URL, CUSTOM_LLM_KEY, CUSTOM_LLM_MODEL Any OpenAI-compatible endpoint (Groq, OpenAI, Mistral, OpenRouter, Together)

```env
LLM_PROVIDER=custom
CUSTOM_LLM_URL=https://api.groq.com/openai/v1
CUSTOM_LLM_KEY=gsk_...
CUSTOM_LLM_MODEL=llama-3.3-70b-versatile
```

---

Local scripts (Windows)

Script What it does
install.bat Installs Python, Node.js, PostgreSQL, and dependencies
start_all.ps1 Starts the API (:8080), UI (:3000), and DSH (if needed)
create_shortcut.ps1 Creates a desktop shortcut with the Vishap icon
apply_custom_llm.py Adds the OpenAI-compatible provider to an existing checkout

```
