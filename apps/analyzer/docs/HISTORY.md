# Project history (v5.8 → v7)

The 37 release tags from v5.8 to v6.5.0 (plus the `6.6.0` release) were deleted in
v7: they were snapshots of a product shape that no longer exists. This page keeps
what was worth keeping — **which version carried what, and where its code is** —
so nothing has to be re-derived from memory.

The commits are still in the repository. Every version below can be re-tagged or
checked out with the SHA in the table:

```bash
git tag v5.10.0 9d1cfeb            # recreate a tag
git switch --detach 9d1cfeb        # or just look at it
git push origin v5.10.0            # and publish it again, if ever needed
```

## What each era delivered

**v5.8.x — "make the wheel actually work"** (12–14 Oct 2026)
Prompts shipped inside the wheel, `DATA_DIR` moved out of `site-packages`,
multi-stage Dockerfile, `risk_verdict` for CWE, OWASP memory-safety mapping.

**v5.9.x — the CI/tooling era, one tool per release** (14 Oct)
`--save-baseline` / `--baseline` (fingerprint suppression), `--diff` /
`--changed-only`, `vishap sbom` (CycloneDX 1.6), SARIF 2.1.0 + GitHub Code
Scanning, quality gates with exit codes 0/1/2, inter-file analysis
(`--context-root`), line-level reachability (`entry_point → source → sink`),
compliance mapping (CWE → concrete controls), runbook generation per CWE.
Test count climbed 55 → 145 in a day, driven by dogfood findings.

**v5.10.x — the analysis depth era** (14 Oct)
Formal threat model (P2-10), pluggable LLM providers (any OpenAI-compatible API),
AST-based dataflow analysis (P2-7b), statistical anomaly detection (P2-12),
then four dogfood-driven verdict/PII fixes.

**v5.11.x — breadth and consolidation** (15 Oct)
`risk_verdict` consolidated into `verdict.py`, UI HTTP client extracted, Java and
C taint patterns. This is where `patterns.py` became the shared table it is now.

**v6.0.x — async API** (15–16 Oct)
Job-based analysis (`POST /analyze/async`, `/status`, `/report`), async UI,
test isolation via `conftest.py`, `JobStore` Protocol + `InMemoryJobStore`.

**v6.1.0 — harness + CI** (17 Oct)
DSH harness provider (sync + async), `--mode concurrency` and `--mode contracts`,
`ci.yml` with a 3.11/3.12 matrix, `ruff.toml`, 9 BOM files fixed.

**v6.2.x — distribution** (17 Oct)
PyPI Trusted Publishing (`publish.yml`, OIDC, tag `v*`), version sync.

**v6.3.0 — Next.js dashboard** (17 Oct)
`ui-next/` replaced the Streamlit prototype: Clerk auth, analyze form with
polling, Markdown report view, dark theme.

**v6.4.x — SaaS surface** (18 Oct)
Row-level security on `jobs`, audit export, SSO, marketplace, blog, download
links; legal entity details.

**v6.5.0 — landing + docs** (18 Oct)
Landing page, Docusaurus site, first Docker CI.

**6.6.0 — desktop** (19 Oct)
Tauri shell: native window, auto-start Python, Rust IPC fallback (PNA), memory
job store, Clerk gated for desktop.

**v7 (slim) — one shape per concern**
Streamlit UI, the Ollama provider with its `local` mode, and the whole Docker
distribution were removed, and the DSH harness became the **only** LLM path — the
direct DeepSeek / OpenAI / OpenAI-compatible clients and the `openai` dependency
are gone. One UI (`ui-next/`), one LLM chain (local DSH harness), one distribution
(PyPI) and one process manager (systemd).

## Releases and their commits

| Tag | Commit | Date | What it was |
| --- | --- | --- | --- |
| v5.8 | 4c295bd | 2026-10-12 | JSON download + audit details in UI |
| v5.8.1 | d5ae6b3 | 2026-10-13 | prompts in wheel, `DATA_DIR`, multi-stage Dockerfile |
| v5.8.2 | e4bad9f | 2026-10-13 | CWE verdict, OWASP memory safety, README paths |
| v5.8.3 | ea9305f | 2026-10-14 | version bump 5.8.3 |
| v5.9.0 | c4c8ab9 | 2026-10-14 | baseline |
| v5.9.1 | ca5b572 | 2026-10-14 | diff-aware scan |
| v5.9.2 | 10b9d18 | 2026-10-14 | SBOM (CycloneDX) |
| v5.9.3 | 0bc990b | 2026-10-14 | SARIF 2.1.0 + Code Scanning |
| v5.9.4 | fda4e6e | 2026-10-14 | quality gates + Windows UTF-8 |
| v5.9.5 | eea8e32 | 2026-10-14 | inter-file analysis |
| v5.9.6 | 9598cb7 | 2026-10-14 | false PASS in diff-aware skip-path |
| v5.9.7 | 86bd54a | 2026-10-14 | line-level reachability |
| v5.9.8 | b58a1ca | 2026-10-14 | compliance mapping |
| v5.9.9 | 03fe7b0 | 2026-10-14 | runbook generation |
| v5.10.0 | 9d1cfeb | 2026-10-14 | formal threat model |
| v5.10.1 | 8e322d4 | 2026-10-14 | pluggable LLM providers |
| v5.10.2 | e635b85 | 2026-10-14 | dataflow analysis |
| v5.10.3 | 706f2c4 | 2026-10-14 | docs: test-suite sync |
| v5.10.4 | 34d1c5b | 2026-10-14 | anomaly detection |
| v5.10.5 | 60fddcc | 2026-10-14 | async import + UI API key |
| v5.10.6 | 7c9c48a | 2026-10-14 | verdict on critical nodes |
| v5.10.7 | 41d7ffa | 2026-10-14 | PII on copyright headers |
| v5.11.1 | 7879a26 | 2026-10-15 | verdict checks stage-2 findings |
| v5.11.2 | 4edfa47 | 2026-10-15 | verdict consolidated into `verdict.py` |
| v5.11.3 | 67af659 | 2026-10-15 | UI `api_client.py` |
| v5.11.5 | a327edc | 2026-10-15 | Java taint patterns |
| v5.11.6 | 50eb802 | 2026-10-15 | C taint patterns |
| v6.0.0 | fd1fdd4 | 2026-10-15 | async API (jobs) |
| v6.0.1 | a6400ad | 2026-10-15 | async UI, dataflow rendering |
| v6.0.2 | aa7bf3f | 2026-10-16 | test isolation, version test |
| v6.0.3 | 6b2c472 | 2026-10-16 | `JobStore` Protocol + in-memory |
| v6.2.0 | 0a1054f | 2026-10-17 | PyPI Trusted Publishing |
| v6.2.1 | 37afcf5 | 2026-10-17 | release workflow + version sync |
| v6.3.0 | 20f7e45 | 2026-10-17 | Next.js dashboard |
| v6.4.0 | f24eadc | 2026-10-18 | RLS, audit export, SSO, marketplace, blog |
| v6.4.1 | 762ad64 | 2026-10-18 | legal details |
| v6.5.0 | 489c797 | 2026-10-18 | landing, docs site, Docker CI |

## What survived the deletion

Everything that was load-bearing lives in the current tree, not in the tags:

- **Deterministic tools** — `sarif`, `sbom`, `quality_gate`, `diff`, `baseline`,
  `reachability`, `dataflow`, `compliance`, `runbook`, `anomaly`, `deps`. These
  are `src/tools/*.py`; the tags were mostly the order in which they appeared.
- **`patterns.py`** — the shared table (taint sources/sinks, CWE maps, compliance,
  runbooks, anomaly config, critical-risk patterns) that every v5.11+ release
  added a row to.
- **Audit trail contract** — `material_hash` vs `material_hash_full`, additive-only
  keys. Unchanged since v5.8.
- **Case studies and evidence** — `docs/case-studies/`, `docs/PROOF.md`,
  `docs/HANDOFF.md` (the block-by-block log of what broke and why),
  `examples/`.
- **`CHANGELOG.md`** — the human-readable feature history.

## What died, and why

| Removed | Why |
| --- | --- |
| Streamlit UI (v5.x–v6.2) | duplicated `ui-next/`; every change cost twice |
| Ollama + `mode=local` (v5.x–v6.6) | second LLM stack to maintain |
| Direct DeepSeek / OpenAI clients (v5.8–v6.6) | the DSH harness is the single LLM path since v7 |
| Docker *as a distribution channel* (v5.8–v6.6) | PyPI covers install; the image is back as an optional, host-harness-backed stack, and nothing is pushed to a registry |

The lessons from those eras are recorded where they are still useful:
`docs/HANDOFF.md` for the operational rakes, `docs/LESSONS.md` for the distilled
rules (what a proof must contain, what to check before claiming a result), and
`docs/TAURI.md` for the desktop path.
