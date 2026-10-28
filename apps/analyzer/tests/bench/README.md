# Benchmarks

Two sets of deliberately vulnerable Flask code with ground truth.

| Set | Files | Bugs | Use |
|---|---|---|---|
| `planted` | `planted_app.py` (+ `fixed_app.py`, every bug fixed) | 18 | regression check; the first line says the file is vulnerable, so any model is primed |
| `blind` | `blind/shop_service.py`, `blind/orders_service.py` | 18 + 16 | the comparison: nothing in the code hints at a bug |

The rules were written together with `planted`, so the engine's 18/18 there says only that nothing regressed.
`blind/orders_service.py` was written afterwards and the rules were not changed for it: the engine finds
6 of 16, the rest (IDOR, client-supplied price, float money, swallowed payment error, SSRF, open redirect,
unsigned token, ...) has to come from a model.

## Engine only (no LLM, no key)

    python -m tests.bench.score engine planted
    python -m tests.bench.score engine blind

## Vishap against a plain model, same material, same prompt

1. For each file in `blind/`, give the plain model this and nothing else, in a fresh chat with no tools:
   "Review this file for security problems and logic bugs. List every issue with line numbers." + the file.
2. Give the same file to Vishap (UI, CLI or MCP tool) with the same file name.
3. Save every answer as text, one file per answer, for example `ai_orders.txt`, `vishap_orders.txt`.
4. Score each one against its own file:

       python -m tests.bench.score report ai_orders.txt vishap_orders.txt --set blind --file orders_service.py
       python -m tests.bench.score report ai_shop.txt vishap_shop.txt --set blind --file shop_service.py

The score is keyword based and prints the keyword that matched. Read it, and read the misses. A report that
mentions a bug in passing counts as a hit; a report that finds it but words it differently counts as a miss.
Run each side more than once: one run of a model is a sample, not a score.

What this does not measure: exploit proof (`vishap prove`), verified patches, baselines/diffs and repository
scans. A plain model cannot do those at all, so they are not scored here.
