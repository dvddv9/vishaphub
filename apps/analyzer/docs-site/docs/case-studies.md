# Case Studies

Vishap has been exercised on real open-source code and specifications. Selected results:

## Sakai Java — RequestFilter

- **Input:** a real Java servlet filter from the Sakai project.
- **Result:** D3 report, 11 risk nodes (3 critical), verdict `REQUIRES_REVIEW`.
- **Impact:** the finding drove the `v5.10.5` and `v5.10.6` fixes (critical `risk_nodes` must force a review verdict).

## curl PR #23441

- **Input:** `curl/curl` documentation (`docs/INSTALL.md`).
- **Result:** a documentation PR that encourages verifying the tarball before unpacking.
- **Lesson:** audit output must be turned into a short, human-written contribution — never posted verbatim. See `LESSONS.md`.

## Dogfood

Vishap analyzes its own repository:

- **12 curl docs** (README, SECURITY, HTTP-COOKIES, INSTALL, ...) — 2 SAFE, 10 REQUIRES_REVIEW.
- **curl/lib/socks.c** — the pipeline re-identified the class of CVE-2023-38545 (unvalidated SOCKS handshake buffer).
- **HTTP-COOKIES.md** — a PII false positive (a Unix timestamp matched the passport regex) was found and traced, which led to a defense-in-depth fix in the verdict logic.

Reports live in `docs/case-studies/` in the repository.
