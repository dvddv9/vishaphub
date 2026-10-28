# Multi-Material Case Studies

3 non-code materials analyzed by Vishap V5.8 — proving multi-material capability.

## Summary

| # | Material | Type | Level | Route | Compliance | Cost | Verdict |
|---|----------|------|-------|-------|------------|------|---------|
| 1 | [incident.log](incident-log-pool-exhaustion.md) | `logs` | D1 | incident_triage -> root_cause -> remediation | PCI-DSS | $0.0055 | REQUIRES_REVIEW |
| 2 | [k8s_insecure.yaml](k8s-insecure-config.md) | `config` | D2 | `[]` (EMERGENCY) | PCI-DSS, SECRETS | $0 | REQUIRES_REVIEW |
| 3 | [payment_spec.md](payment-spec-review.md) | `spec` | D2 | stage4 -> stage3 | PCI-DSS | $0.0068 | REQUIRES_REVIEW |

**Total:** 3 analyses, ~$0.0123.

## What this proves

- **`material_type` detection works:** `logs`, `config`, `spec` correctly identified by Stage 0.
- **Adaptive routing:** for `logs`, Conveyor selected `incident_triage`, `root_cause`, `remediation` — not the code-oriented `scanner`/`analyst`.
- **Domain expertise:** LLM applies industry patterns — Stripe/Adyen idempotency, Netflix Hystrix circuit breaker, AWS envelope encryption.
- **Gate precision:**
  - `logs` -> no real secret -> analysis proceeds.
  - `config` -> real `sk_live_...` -> **EMERGENCY_INTERRUPT confirmed**, pipeline stops.
  - `spec` -> PCI-DSS compliance flag, no secret -> LLM emergency **downgraded**, analysis proceeds.
- **Compliance auto-detection:** PCI-DSS triggered on all 3 materials (payment/payments keywords).

## Positioning

Vishap is **not** a code reviewer. It is a **multi-material IT analyst**:
code, config, logs, specs, incidents. This is the differentiation from
CodeRabbit, Qodo, Graphite (code-only).

## Reproduce

    vishap analyze data/real_cases/multi/incident.log
    vishap analyze data/real_cases/multi/k8s_insecure.yaml
    vishap analyze data/real_cases/multi/payment_spec.md
