# Juice Shop dataExport.ts — IDOR + PII leak
**File:** routes/dataExport.ts (~110 LOC) | **Level:** D3 | **Cost:** ~$0.007
## Found
**CRITICAL: IDOR** — `MemoryModel.findAll({ where: { UserId: req.body.UserId } })` — client controls key, no ownership check.
**IMPORTANT:** Email leak in error messages, no rate limit/size bound, no audit log, `solveIf` in loop.
## STRIDE
S: UserId substitution. T: Bearer reuse. R: no audit log. I: email leak. D: DoS via mass export. E: gamification state.
