# Vishap Core

The layer every service shares. It exists because the copies drifted: six modules
lived in two repositories in two slightly different versions, so a fix in limits or
keys had to be made twice and was made once.

## What is here

| Module | Rule |
|---|---|
| `auth.check_key` | one decision, explicit flags: static key, bring-your-own-key, public demo, unconfigured |
| `rate_limit.Limiter` | per-client bucket + global bucket; the stricter one wins |
| `rate_limit.Bucket` | token bucket with refill, no framework, no clock magic |

Still to move (the remaining four): `job_store`, `llm_config`, `jobs`, `reports`.
They are the reason this package exists; they land here once the services stop
importing their own copies.

## Why no FastAPI

The rule lives in plain Python so it can be tested and reused from a stdlib HTTP
handler, a FastAPI route, or a CLI. The framework adapter turns a `Decision` into a
response; the decision itself knows nothing about HTTP.

## Keys

```python
check_key(provided, KeyPolicy(expected_key="k"))                 # ALLOW / MISSING / INVALID
check_key("", KeyPolicy(expected_key="k", public_demo=True))     # ALLOW — the limit bounds the spend
check_key("", KeyPolicy(require_user_key=True))                  # MISSING — nothing to fall back to
check_key("", KeyPolicy())                                       # UNAVAILABLE — never allow by accident
```

Matching uses `hmac.compare_digest`: a key comparison that leaks timing is a key
comparison that gets guessed.

## Limits

```python
lim = Limiter(per_client=7, per_client_seconds=60, global_cap=30, global_seconds=86400)
lim.allow("1.2.3.4").allowed
```

Two limits, two purposes: the per-client one protects the queue, the global one
protects the owner's budget. Neither is a market-share tool.

## Status

`0.1.0` — keys and limits work. Tests are deliberately left for the end of the build.
