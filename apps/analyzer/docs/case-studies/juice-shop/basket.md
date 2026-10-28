# Juice Shop basket.ts — IDOR
**File:** routes/basket.ts (~40 LOC) | **Level:** D2 | **Cost:** ~$0.007
## Found
**CRITICAL: IDOR / Broken Access Control**
`BasketModel.findOne({ where: { id } })` uses `id` from `req.params` without filter by `user.bid`. `challengeUtils.solveIf` detects violation but does not block — classic "detect but don't prevent". Any authenticated user reads any basket by id.
## Fix
Add `basket.userId === user.bid` check. Remove reliance on challenge hook.
