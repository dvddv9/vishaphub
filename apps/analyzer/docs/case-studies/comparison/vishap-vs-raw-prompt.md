# Case Study: Conveyor vs Raw Prompt — Metadata Validation

> **⚠️ LEGACY (pre-v5.7):** `material_hash` truncated to 16 hex.
> Source material and JSON no longer available.


**Date:** 2026-10-11
**Material:** Same spec — Python 50k RPS transaction system (FastAPI + Kafka + Citus + Redis + EKS + Vault)
**Task:** Compare Conveyor pipeline vs raw LLM prompt (same content, no pipeline)

---

## Setup

Two runs on the **same material**:

- **Vishap V5.8** — 6-stage pipeline with audit trail, cost tracker, retry, gate
- **Raw Prompt** — ChatGPT with the Conveyor prompt (`conveyor/*.md`) but no pipeline

Both produced similar **content**. The difference is in **metadata validity**.

---

## Comparison

| Criterion | Vishap V5.8 | Raw Prompt |
|-----------|---------------|------------|
| **material_hash** | `sha256:87dfedb11a3b4826...` (real, 64 hex chars) | `sha256:fintech50k...` (**fake**, not SHA-256) |
| **audit_id** | `audit-2026-10-11-b6cd0a` (md5 of timestamp, hex-valid) | `audit-2026-10-11-f7k2m9` (`k2m9` not hex, **hallucinated**) |
| **ROUTE stage order** | `stage1 → stage2 → stage3 → stage4 → stage5` (correct) | `stage1 → stage2 → stage4 → stage3 → stage5` (**broken**) |
| **D-level** | `D3` (correct for spec, <3000 tokens) | `D4` (**inflated**, does not match material size) |
| **Parallels (Citus/KEDA)** | Stage3_researcher called systematically when `research_first=true` | Added "parallels for Citus/KEDA" — **improvised** |
| **Metadata** | Strictly follows Conveyor rules (`hashlib`, `md5`, stage order) | **Hallucinations**: hash, audit_id, stage order, level |
| **Cost per analysis** | `$0.011264` (measured) | Not specified |
| **Retry on JSON parse fail** | yes | no |
| **Emergency gate** | yes (`llm_emergency_downgraded`) | no |
| **Compliance flags** | yes `['PCI-DSS']` (regex-based) | LLM-based |
| **PII detection** | Regex (no hallucination) | LLM-based |

---

## Content Comparison

**Content is comparable.**

Both identified:
- Redis SETNX inverted pattern
- TLS rotation without dual-CA
- Citus write throughput bottleneck
- Missing retry/backoff/circuit breaker
- Kafka MITM risk
- No audit log (PCI DSS Req.10)
- 12 STRIDE threats

**Raw prompt** — more compact, business-oriented.
**Conveyor** — more detailed, with verified metadata.

---

## Where Conveyor Wins

### 1. Valid metadata

- **`material_hash`** — computed via `hashlib.sha256` — **real**
- **`audit_id`** — `md5(timestamp).hexdigest()[:6]` — **hex-valid**
- Raw prompt **hallucinates** these — looks plausible, but is **invalid**

### 2. Systematic structure

- **Stage order** — `stage1 → stage2 → stage3 → stage4 → stage5` — correct
- Raw prompt — `stage1 → stage2 → stage4 → stage3 → stage5` — **broken**

### 3. Correct D-level

- Material is a spec (~500 lines) → **D3**
- Raw prompt returned **D4** (inflated)

### 4. No hallucinated numbers

- Cloud cost: Conveyor says `unknown` if baseline not in material
- Raw prompt **invents** `$12k/mo infra + $50k dev`

### 5. Pipeline features

- **Retry** on JSON parse fail
- **Cost tracker** ($0.011264)
- **Emergency gate** (`llm_emergency_downgraded`)
- **Compliance flags** (regex)
- **PII detection** (regex)

---

## Where Raw Prompt Is Comparable

- **Content quality** — comparable
- **Risk nodes** — 7 vs 6 (both strong)
- **Threat model** — 7 components vs 7 TB (both)
- **Parallels** — 5 vs 10 (raw prompt more compact)
- **Action plan** — both have NOW/TODAY/TOMORROW/LATER

---

## Positioning

**Wrong:** "Conveyor = consulting worth $50k-100k, but free."
**Why:** Overpromise. Not defensible.

**Right:**
> Vishap is a **production-ready pipeline** for senior-level first-pass IT analysis.
> Difference from a raw prompt: **valid metadata** (real SHA-256, audit_id), **systematic structure** (stage order, D-level), **no hallucinated numbers**, plus **retry, cost tracking, emergency gate**.
> **Not "better than ChatGPT" — but "auditable and reproducible".**

---

## Why This Matters

A raw prompt can produce **plausible-looking** reports — with fake hashes, fake audit IDs, broken stage order, inflated levels.

In **compliance** (PCI DSS, GDPR, HIPAA) — **metadata validity is critical**. You cannot audit a report with a fake `material_hash`.

**Vishap guarantees:**
- Real `sha256` — reproducibility
- Real `audit_id` — traceability
- Correct stage order — systematic process
- Correct D-level — material classification
- **No hallucinated numbers** — honesty

**This is the difference between a "prompt" and a "product".**

---

## Reproduce

    vishap analyze examples/multi/python_50k_rps_spec.txt

Raw prompt run: copy `conveyor/*.md` prompts into ChatGPT, paste same material.
