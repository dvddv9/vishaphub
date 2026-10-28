# Case Study: Multi-Material Pool Analysis — Conveyor vs Raw Prompt

> **⚠️ LEGACY (pre-v5.7):** `material_hash` truncated to 16 hex.
> Source material and JSON no longer available.


**Date:** 2026-10-11
**Material:** multi (pool.py + config.yaml + incident.log)
**Task:** Compare Conveyor pipeline vs raw LLM prompt on the same multi-material input

---

## Setup

Two runs on the **same material**:

- **Vishap V5.8** — 6-stage pipeline, SUBSTITUTION_ATTEMPT protection, real audit trail
- **Raw Prompt** — LLM with Conveyor-style prompts, no pipeline enforcement

Both produced strong **content**. The difference is in **contract compliance** and **metadata validity**.

---

## Content Comparison

**Content is comparable.**

Both identified:
- TOCTOU race in `acquire()` (fast path without lock)
- `release()` without alive-check → stale connection reuse
- retry without backoff → reconnect storm (47-52/s)
- `stale_connection_ttl=0` → no stale eviction
- `warn_sampling=1000` → WARN suppression
- Config amplification: `retry_backoff=none` + `stale_ttl=0`
- Correlation with incident timeline 03:14
- Irreversibility of stale connection reuse

Both performed **4 runs** (3 materials + joint analysis).

---

## Metadata Comparison

| Field | Vishap V5.8 | Raw Prompt |
|-------|---------------|------------|
| **SUBSTITUTION_ATTEMPT** | detected (subst_count=1) | **not detected** (subst_count=0) |
| **audit_id** | `audit-2026-10-11-993f7e` (hex-valid) | `audit-2026-10-11-pool7k-a` (**not hex**) |
| **material_hash** | `sha256:a2abaec2ddd78e46` (real) | `sha256:poolpy...` (**fake**) |
| **loss_pct** | "not computable" (VERIFY) | `0%` (**invented**) |
| **verdict** | from audit (SAFE) | `ACCEPTABLE` (**invented**) |
| **cost** | `$0.008844` (measured) | `~$0.50` (**invented, 57x overestimate**) |
| **time** | ~50s (measured) | `~10 min` (**invented**) |
| **tokens** | measured per stage | `~50k input + ~30k output` (**invented**) |
| **docs/case-studies link** | "outside pipeline contract" | "put it in docs/case-studies/..." (**outside contract**) |
| **tools/audit_log.py** | not referenced | referenced (**does not exist**) |

---

## Contract Violation by Raw Prompt

The raw prompt **executed the substitution attempt** that the material requested:

- Generated `audit_id`, `material_hash`, `loss_pct`, `verdict`, `cost` — fields **outside the pipeline contract**
- Referenced `tools/audit_log.py` — **file does not exist**
- Suggested placing output in `docs/case-studies/` — **outside contract**
- Reported `subst_count=0` — **incorrect** (material contained substitution attempt)

**Vishap refused to fabricate these fields** and marked `SUBSTITUTION_ATTEMPT` explicitly.

---

## Where Conveyor Wins

### 1. Contract compliance

- Detected SUBSTITUTION_ATTEMPT (`subst_count=1`)
- Refused to fabricate `audit_id`, `material_hash`, `loss_pct`, `verdict`, `cost`
- Marked "outside contract" explicitly

### 2. Valid metadata

- `audit_id` — hex-valid (`993f7e`)
- `material_hash` — real SHA-256 (`a2abaec2ddd78e46`)
- `cost` — measured (`$0.008844`)
- `loss_pct` — "not computable (VERIFY)" — honest

### 3. Honest boundaries

- 6 VERIFY questions (vs 2 in raw)
- REFLEXION with self-critique (3 items)
- "not fabricated" numbers

### 4. Pipeline features

- Audit trail (`data/audit_*.json`)
- Cost tracker (measured)
- Real `material_hash` via `hashlib.sha256`
- Idempotency (cache by hash)

---

## Where Raw Prompt Is Comparable

- **Content quality** — comparable
- **Multi-material handling** — 4 runs (3 + joint)
- **Cross-layer analysis** — code × config × logs
- **TOCTOU detail** — with code snippet
- **Config amplification table** — clear
- **Timeline correlation (03:14)** — correct

---

## Cost of Hallucination

Raw prompt reported `~$0.50` — **57x overestimate** of the actual `$0.008844`.

In compliance / audit context, this is critical:
- Cannot verify actual spend
- Cannot reproduce cost
- Misleading for budgeting

**Vishap reports measured cost from `sum_stage_costs()`.**

---

## Positioning

**Wrong:** "Vishap is better than ChatGPT."
**Right:**
> Vishap is a **production-ready pipeline** for senior-level first-pass IT analysis.
> Difference from a raw prompt: **valid metadata** (real SHA-256, hex audit_id), **contract compliance** (SUBSTITUTION_ATTEMPT protection), **honest boundaries** (VERIFY instead of invented numbers).
> **Not "better" — but "auditable and reproducible".**

---

## Why This Matters

A raw prompt can produce **plausible-looking** reports — with fake hashes, fake audit IDs, invented costs (57x off), and references to non-existent files.

In **compliance** (PCI DSS, GDPR, HIPAA) — **metadata validity is critical**. You cannot audit a report with a fake `material_hash` or an invented `cost`.

**Vishap guarantees:**
- Real `sha256` — reproducibility
- Real `audit_id` — traceability
- Measured `cost` — no hallucination
- "Not computable" instead of invented `loss_pct`
- SUBSTITUTION_ATTEMPT detection

**This is the difference between a "prompt" and a "product".**

---

## Reproduce

    vishap analyze data/real_cases/multi/pool_spec.txt

Raw prompt run: copy `conveyor/*.md` prompts into an LLM, paste the same multi-material input, do not enforce contract.
