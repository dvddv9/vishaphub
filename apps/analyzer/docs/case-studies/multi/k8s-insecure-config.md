# Case Study: Kubernetes Config — EMERGENCY_INTERRUPT (Real Secret)

**Material type:** `config`
**Level:** D2
**Route:** `[] (EMERGENCY_INTERRUPT, confirmed by audit)`
**Compliance:** PCI-DSS, SECRETS
**Cost:** $0 (stopped before LLM stages)
**Session:** sess-2026-10-10-150818
**Verdict:** REQUIRES_REVIEW

**Key findings:** privileged: true, hostNetwork, hostPID, docker-sock mount, DB_PASSWORD=admin123, STRIPE_SECRET_KEY=sk_live_..., JWT_SECRET=secret. Gate confirmed real secret -> stop.

---

## Vishap Output

⛔ INTERRUPTED: EMERGENCY

[EMERGENCY]
Stage 0 обнаружил критический риск → pipeline остановлен.
[TRIGGER] flags: ['EMERGENCY_INTERRUPT']
[REASON] level: D2, route: []


[AUDIT_TRAIL]
audit_id: audit-2026-10-10-81112c
material_hash: sha256:184ed8c1860e749c2ff02f94f4404070afd580ea7b67e5143a8c0dd8512460b3
pii_detected: false
compliance_flags: ['PCI-DSS', 'SECRETS']
critique_verdict: REQUIRES_REVIEW

---

## Reproduce

    vishap analyze data/real_cases/multi/k8s_insecure.yaml
