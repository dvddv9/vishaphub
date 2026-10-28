# Case Study: D3 (Conveyor) vs D4 Fallback (Raw Prompt)

> **⚠️ LEGACY (pre-v5.7):** `material_hash` truncated to 16 hex.
> Source material and JSON no longer available.


**Date:** 2026-10-11
**Material:** Same spec — 100-200k RPS payment platform, PCI DSS + GDPR
**Task:** Compare two modes — full pipeline (D3) vs fallback (D4)

---

## Setup

Two runs on the **same material**:

- **D3 (Conveyor)** — full 6-stage pipeline, `force_emergency=false`, `return_to_stage2=true` acknowledged
- **D4 (Raw Prompt)** — fallback mode, `CRITICAL_ESCALATION (4 conflicts)`, "delivering reduced final"

Both produce strong content. The difference is in **metadata validity** and **pipeline transparency**.

---

## Comparison

| Criterion | D3 (Conveyor) | D4 Fallback (Raw Prompt) |
|-----------|---------------|--------------------------|
| **Focus** | Solution: PG-centric architecture, crypto-shredding, outbox+Debezium | Honest acknowledgement: 4 unsolvable dilemmas |
| **Resilience** | 3/10 (low, but plan exists) | 2/10 → 5/10 after fixes (acknowledges limits) |
| **ROUTE** | `stage1 → stage2 → stage3 → stage4 → stage5` | `stage1 → stage2 → stage4 → stage3 → stage5` (**broken**) |
| **Idempotency** | PG advisory lock + unique constraint (**canonical**) | Redis SETNX + PG unique, **race acknowledged as inevitable** |
| **GDPR vs PCI DSS** | Crypto-shredding (ENISA 2021, ICO) — **legally correct** | Direct conflict, deferred to LATER (legal review) |
| **Multi-region** | Quorum-based replication (Spanner OSDI 2012) | Sync at 200k RPS — **acknowledged impossible** |
| **Hot shard** | Composite key `(merchant_id, bucket_id)` | SLA breach acknowledged as inevitable |
| **Threat model** | Full STRIDE (8 threats, 4 critical) | Compact STRIDE (5 rows, key threats covered) |
| **Action plan** | NOW/TODAY/TOMORROW/LATER with specifics | NOW/TODAY/TOMORROW/LATER with boundary acknowledgement |
| **Reflexion** | Pipeline limits acknowledged (`return_to_stage2`, `json_ok=false`) | Material limits acknowledged ("4 dilemmas not simulated") |
| **material_hash** | `sha256:35b96b43c9029e5b` (real, hex) | `sha256:fintech200k...` (**fake**, not SHA-256) |
| **audit_id** | `audit-2026-10-11-8a591c` (md5, hex-valid) | `audit-2026-10-11-x9p4q2` (`x9p4q2` **not hex**) |
| **D-level** | `D3` (correct for spec, <3000 tokens) | `D4` (**inflated**, material is small spec) |
| **Cloud cost** | `current $N (не указано — VERIFY)` | `$35k/mo infra + $100k dev` (**invented**) |
| **Markdown** | Clean Markdown blocks | **Broken JSON** (no code fence) |
| **Compliance flags** | `['PCI-DSS', 'GDPR']` (regex) | `[PCI-DSS, GDPR]` (LLM) |

---

## Content Comparison

**Content is comparable.**

Both identified:
- Redis SETNX race condition
- Hot shard 40% (80k RPS on one shard)
- Kafka at-least-once without dedup
- TLS rotation without dual-CA
- GDPR vs PCI DSS legal conflict
- Multi-region sync impossible at 200k RPS

**D3 (Conveyor)** — more detailed, with canonical patterns and valid metadata.
**D4 (Raw Prompt)** — more compact, stronger tone of honest acknowledgement.

---

## Where Conveyor Wins (D3)

### 1. Valid metadata

- `material_hash` — computed via `hashlib.sha256` — **real**
- `audit_id` — `md5(timestamp).hexdigest()[:6]` — **hex-valid**
- Raw prompt (D4) — **hallucinates** both

### 2. Systematic structure

- **Stage order** — `1→2→3→4→5` (with parallel `stage3∥4`) — correct
- Raw prompt — `1→2→4→3→5` — **broken**

### 3. Correct D-level

- Material is a spec (~50 lines) → **D3**
- Raw prompt returned **D4** (inflated, no reason)

### 4. No hallucinated numbers

- Cloud cost: Conveyor says `unknown` if not in material
- Raw prompt **invents** `$35k/mo + $100k + $50k`

### 5. Canonical patterns

- **PG advisory lock** instead of Redis SETNX (Brandur Leach, PostgreSQL docs)
- **Outbox + CDC (Debezium)** — Richardson "Microservices Patterns"
- **Crypto-shredding** — ENISA 2021, ICO, PCI DSS v4.0 Req 3.2.1
- **Quorum-based replication** — Spanner OSDI 2012, CockroachDB

### 6. Clean Markdown

- Structured blocks (`[ECHO]`, `[CONCLUSION]`, etc.)
- Raw prompt — **broken JSON** at the end

---

## Where Raw Prompt Wins (D4)

### 1. Stronger tone of honesty

- **"FALLBACK MODE: 4 unsolvable dilemmas"** — explicit
- **"Pipeline cannot solve the unsolvable"** — honest
- **"ACKNOWLEDGEMENT: some requirements are impossible — document it"** — direct

### 2. Explicit boundary acknowledgement

- D4 says: "not simulated, honestly acknowledged"
- This is a **mature** approach — better than faking a solution

### 3. Resilience trajectory

- `2/10 → 5/10 after fixes` — with boundary acknowledgement
- D3 says `3/10` — without trajectory

---

## Positioning

**Wrong:** "Conveyor = Deloitte for $0.01."
**Why:** Overpromise. Not defensible.

**Right:**
> Vishap is a **production-ready pipeline** for senior-level first-pass IT analysis.
> It has two modes:
> - **D3 (solution mode):** canonical patterns, valid metadata, systematic structure
> - **D4 (fallback mode):** honest boundary acknowledgement, no fake solutions
> **Difference from raw prompt:** valid metadata (real SHA-256, audit_id), systematic stage order, no hallucinated numbers, clean Markdown.
> **Not "better than ChatGPT" — but "auditable and reproducible".**

---

## Why This Matters

Two modes show **maturity**:

1. **D3 (solution)** — when a solution exists, Conveyor builds it with canonical patterns.
2. **D4 (fallback)** — when requirements are impossible, Conveyor acknowledges boundaries.

**A raw prompt can produce both** — but with **fake metadata** (`fintech200k...`, `x9p4q2`), **broken stage order** (`1→2→4→3→5`), **inflated level** (`D4`), and **invented numbers** (`$35k/mo`).

**In compliance** (PCI DSS, GDPR) — **metadata validity is critical**. You cannot audit a report with a fake `material_hash`.

**Vishap guarantees:**
- Real `sha256` — reproducibility
- Real `audit_id` — traceability
- Correct stage order — systematic process
- Correct D-level — material classification
- **No hallucinated numbers** — honesty
- **Two modes** — solution and boundary acknowledgement

**This is the difference between a "prompt" and a "product".**

---

## Reproduce

    vishap analyze data/real_cases/multi/100k_rps_gdpr_spec.txt

Raw prompt run: copy `conveyor/*.md` prompts into ChatGPT, paste same material, request fallback mode.
