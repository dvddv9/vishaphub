<!-- DRAFT — not sent. Review before sending to security@curl.se. -->
<!-- Placeholders to fill: [Name], [GitHub handle], [Affiliation], [email]. -->

## 1. Subject

| Field | Value |
|---|---|
| **To** | security@curl.se |
| **From** | [Name] ([GitHub handle], [Affiliation]) · [email] |
| **Date** | 2026-10-18 |
| **Subject** | Security analysis: potential race condition and NUL bypass in lib/cookie.c |

## 2. Greeting

Hello curl security team,

## 3. Introduction

My name is [Name] ([GitHub handle]). I have contributed to curl (PR #23441, documentation), and I run an automated static-analysis tool called Vishap that I maintain.

I ran it over two source files from curl — `lib/cookie.c` and `lib/http2.c` — and this message summarises what it reported. **These are heuristic findings from a language model, not a proof of concept.** I have not built a reproducer, and I am not claiming a CVE. I would rather send an imperfect report than sit on something real, so please treat this as a triage candidate list.

Both files were analysed as **truncated slices** (see §6). That limits confidence, and I have tried to mark where it matters.

## 4. Findings in lib/cookie.c

Snapshot: `2b72416`. Four findings, one of which is the reason I am writing.

| ID | CWE | Severity | Where | What |
|---|---|---|---|---|
| SEC-3 | CWE-362 | critical | `remove_expired`, `storecookie` | Unsynchronised mutation of shared `CookieInfo` state |
| SEC-1 | CWE-20 | important | `invalid_octets` | NUL byte terminates validation early; the tail is not checked |
| SEC-2 | CWE-125 | important | `storecookie` | Out-of-bounds read indexing the cookie pieces array |
| SEC-4 | CWE-459 | important | `storecookie` | On allocation failure the cookie is left partially initialised |

**SEC-3 (CWE-362) — the one I would look at first.** `remove_expired` and `storecookie` mutate `ci->numcookies`, `next_expiration` and the per-cookie fields without any synchronisation visible in the analysed slice. If a share handle is used from more than one thread, that is a data race with the usual consequences: corrupted list state, or use of a partially updated `CookieInfo`. The safety of this code appears to depend on a share-lock contract that is not expressed in this file — I could not verify `curl_share.c` because it was outside the slice, so treat the finding as unproven rather than confirmed.

**SEC-1 (CWE-20).** `invalid_octets` walks the buffer as `while (len && *p)`, so an embedded NUL ends validation early while the rest of the buffer remains in use downstream. The value that was validated and the value that is consumed can differ.

**SEC-2 (CWE-125).** `storecookie` indexes the cookie pieces array without checking that its size assumption holds. If the caller contract is violated, this is an out-of-bounds read rather than a crash on a controlled path.

**SEC-4 (CWE-459).** If allocation fails partway through `storecookie`, the cookie is left partially filled and correctness depends on the caller invoking `freecookie`. Worth checking whether every caller does.

## 5. Findings in lib/http2.c

Snapshot: `3661f39`. Five findings, all on error paths; the happy path looked correct to the tool.

| ID | CWE | Severity | Where | What |
|---|---|---|---|---|
| SEC-1 | CWE-252 | important | `h2_stream_ctx_create` | Return values of stream initialisers are not checked |
| SEC-2 | CWE-459 | important | `cf_h2_ctx_free` | Partial initialisation of `cf_h2_ctx` on the free path |
| SEC-3 | CWE-617 | important | `DEBUGASSERT(0)` reachable from input handling | In release builds the assert compiles out and the function returns NULL |
| SEC-4 | CWE-754 | optional | `cf_h2_update_settings` | Error from submit leaves `initial_win_size` not updated — internal state desync |
| SEC-5 | CWE-362 | optional | `nghttp2_session` usage | Single-threaded multi-handle contract is not documented in the file |

The three "important" ones share a theme: failure of an initialiser is not propagated, so a later stage operates on a structure that exists but is not configured. On OOM these are reachable, though I have not demonstrated which of them turns into an observable failure.

SEC-4 and SEC-5 are marked optional because they may be intentional: `initial_win_size` may be deliberately left stale, and the single-threaded contract may be documented elsewhere. I flag them because the tool could not find that contract in the file.

## 6. Context and provenance

The analysed material is fixed by hash and commit, so you can tell exactly what produced these results:

| File | `material_hash` | `provenance_commit` |
|---|---|---|
| `lib/cookie.c` | `sha256:090701b94535c430616f0cb6e5499f88b938b73fbadfea907821a75a1a142e47` | `2b72416` |
| `lib/http2.c` | `sha256:5b4af1f1ac668e397c5b21fca9cd26ecc7fdb032ccc6080526edced495c863e0` | `3661f39` |

Line numbers are deliberately omitted: they depend on the exact snapshot, and quoting them from memory would be worse than not quoting them at all. The reports referenced in §8 contain per-finding detail tied to these hashes.

## 7. Caveats

I want to be explicit about the limits of this report, because overstating it would waste your time:

- **No proof of concept.** Nothing here has been executed or fuzzed. Each finding needs a human to confirm reachability.
- **Heuristic analysis.** The findings come from a language model reading the code, not from a sound static analyser. False positives are expected — a substantial fraction of the "important" items may fall into that bucket.
- **Truncated input.** `lib/cookie.c` was cut inside `parse_first_pair`, and the HTTP/2 analysis covers a slice of the connection filter cut inside `cf_h2_update_local_win`. Full translation units were not available, so control flow across the cut is not assessed.
- **No tree-sitter coverage for C.** The tool fell back to manual reading for these files, which is why some findings are marked "verify".
- **Possibly already known.** Some of this may be fixed, documented as intentional, or reported before. If so, a one-line reply is enough and I will close it out.

## 8. Offer

If any of this is useful, I can provide:

- the full reports as Markdown (per-finding detail, STRIDE table, refactoring options, and the audit trail with both hashes), or
- minimal test cases for the two findings I consider most concrete — the NUL truncation in `invalid_octets` and the unchecked initialisers in `h2_stream_ctx_create`,

whichever is more useful to you. I am also happy to re-run the analysis on current `master` if the snapshots above are older than what you care about.

I am not asking for credit and I am not setting any disclosure deadline — this is your process, and I will follow your guidance on what to do with it.

## 9. Closing

Best regards,
[Name]
[GitHub handle]
[email]
