---
title: "Case Study: Vishap on curl (cookie.c + http2.c)"
date: 2026-10-18
tags: [case-study, security]
description: Two production files from curl, nine findings, five CWE classes.
---

We pointed Vishap at two files from curl: `lib/cookie.c` and `lib/http2.c`.
Between them it reported nine findings across five CWE classes. None is a proven
vulnerability — these are triage candidates — but the shape of the results is
worth writing down.

{/* truncate */}

## lib/cookie.c — one critical

The critical finding is a data race (`CWE-362`): `remove_expired` and
`storecookie` mutate the shared cookie list without synchronisation visible in
the file. Whether that is exploitable depends on a share-lock contract defined
elsewhere — which is exactly why the report says `REQUIRES_REVIEW` rather than
asserting a vulnerability.

Three further findings: a NUL byte ends validation early in `invalid_octets`
(`CWE-20`), an out-of-bounds read when indexing the cookie pieces array
(`CWE-125`), and a partially initialised cookie left behind on allocation
failure (`CWE-459`).

## lib/http2.c — error paths

The HTTP/2 file produced five findings, all on error paths; the happy path
looked correct. Return values of stream initialisers go unchecked (`CWE-252`),
`cf_h2_ctx_free` assumes a partially initialised context (`CWE-459`), a reachable
`DEBUGASSERT(0)` compiles out to a silent `NULL` in release builds (`CWE-617`),
and two optional items: window-size desync after a failed submit (`CWE-754`) and
an unwritten single-thread contract (`CWE-362`).

## What the reports looked like

Each analysis produced the same structure: findings with CWE and severity, a
STRIDE model tied to those findings, three refactoring options with effort
estimates, and an audit trail with both the analysed-slice hash and the original
material hash.

For `cookie.c` the recommended option was contract-hardening: fix the three
local defects in two to three days and leave the locking architecture alone
until someone proves concurrent access matters. For `http2.c` the same — the
three important findings are all "propagate the failure" changes, not redesigns.

Read the full case studies:
[cookie.c](/docs/case-studies/curl-cookie-c) and
[http2.c](/docs/case-studies/curl-http2-c).

## The honest caveats

- No proof of concept was built; nothing was fuzzed.
- The material was truncated, which limits confidence in control flow across the
  cut.
- Heuristic LLM analysis produces false positives. Some of these nine may be
  wrong, and some may already be known to curl's maintainers.

We drafted a disclosure note to `security@curl.se` describing both files. It is
not sent yet.
