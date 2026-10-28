# Case Study: FastAPI

**Source:** fastapi/routing.py
**Level:** D4
**Cost:** $0.0082
**Truncated:** Yes (259k to 12k chars)
**Session:** sess-2026-10-10-132733
**Verdict:** SAFE

---

## What Vishap found

### 1. CRITICAL - OOM via id(func)

**Problem:**

    _endpoint_context_cache[id(func)] = context

id() is not stable across garbage collection. Python may reuse the same id value for a different function after the original is GC'd. This leads to:

- Unbounded cache growth, OOM
- Wrong context returned for a different function

**Fix:** Use WeakKeyDictionary or store context on function via func.__dict__.

---

### 2. CRITICAL - Vendored divergence from Starlette

**Problem:**

request_response and websocket_session are copied from Starlette but modified. Comments claim "Copy of starlette.routing.*" but code diverges.

**Risk:**

- Upstream Starlette fixes will not arrive
- Comments claiming copy are misleading
- Private imports contradict vendored to avoid private symbols

**Fix:** Either return to dependency or document divergence with version pin.

---

### 3. IMPORTANT - Memory leak in async task

**Problem:**

run_in_threadpool is called without timeout. Sync endpoints may hang and block the thread pool.

**Fix:** Add timeout via asyncio.wait_for.

---

### 4. IMPORTANT - ResponseValidationError leaks raw content

**Problem:**

ResponseValidationError.body contains raw response_content + EndpointContext. This leaks into logs/responses.

**Fix:** Sanitize body before logging.

---

### 5. IMPORTANT - Misleading comments

**Problem:**

Comments claim copy of starlette.routing but code is modified. Three documented divergences contradict.

**Fix:** Update comments, add changelog.

---

## Why this matters

A senior engineer with security focus would find id(func) OOM in 30 minutes.

**Vishap found it in 60 seconds.**

Cost: **$0.0082**.

---

## Reproduce

    vishap analyze data/real_cases/fastapi_routing.py
