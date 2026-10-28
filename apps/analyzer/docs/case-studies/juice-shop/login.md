# Case Study: OWASP Juice Shop — login.ts (EMERGENCY)

**Source:** `login.ts`
**Language:** TypeScript
**Level:** D3
**Cost:** $0
**Verdict:** REQUIRES_REVIEW
**Session:** sess-2026-10-10-193315

---

## Vishap Output

⛔ INTERRUPTED: EMERGENCY

[EMERGENCY]
Stage 0 обнаружил критический риск → pipeline остановлен.
[TRIGGER] flags: ['EMERGENCY_INTERRUPT']
[REASON] level: D3, route: ['stage1', 'stage2', 'stage3', 'stage4']


[AUDIT_TRAIL]
audit_id: audit-2026-10-10-832167
material_hash: sha256:29a6fe160d9a7161842626cbd68fdeabd2245b42086394f3d6a1e94662eb72db
pii_detected: true
compliance_flags: ['GDPR', '152-ФЗ', 'SECRETS']
critique_verdict: REQUIRES_REVIEW

---

## Reproduce

    vishap analyze data/real_cases/juice-shop/login.ts
