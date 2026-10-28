# VishapHub

One repository, one vocabulary, four pieces that used to be five repositories and
were slowly growing apart.

```
apps/
  analyzer/    the security analyst (FastAPI + Next.js UI) — live: vishap-zwpx.onrender.com
  generator/   spec-to-code generator that proves its output — live: vishap-generator.onrender.com
  hub/         carries a request between the three services — live: vishap-hub.onrender.com
  validator/   does the code match the promise (six stages) — live: vishap-validator.onrender.com
packages/
  core/        keys, limits, model choice, report shape — shared by all of them
```

Every directory came in with `git subtree`, so the history of each project is still
here: `git log -- apps/analyzer` reads exactly as it did before the merge.

## Who does what

| Piece | Question | Verdict |
|---|---|---|
| analyzer | is it dangerous? | SAFE / REQUIRES_REVIEW / EMERGENCY |
| validator | does it match the promise? | PASS / NEEDS_REVIEW / FAIL |
| generator | build it from the spec | deliverable + its own checks |
| hub | who asks whom, in what order | the strictest verdict of the run |

The hub never decides the verdict. It carries the request, keeps the session and
returns what the pipeline said — a conversation that changes a verdict turns a proof
into an opinion.

## The order

Generation → validation → security. Dangerous code does not travel further than the
first stage that rejects it. Iterations are capped at three and stop early when no
stage changes its answer.

## Shared rules, one home

`packages/core` holds the four things that used to be copied:

- **keys** — one decision with explicit flags (operator key, bring-your-own-key, public demo, unconfigured);
- **limits** — a per-client bucket and a global one; the stricter wins;
- **model** — operator mode or the caller's key, never blurred;
- **report** — the strictest level survives a merge, conditions travel with it, a partial run says so.

## Running one piece

Each app keeps its own tooling and its own deploy:

```bash
cd packages/core   && pip install -e . && pytest -q
cd apps/validator  && pip install -e . && pytest -q && python -m validator.server
cd apps/hub        && pip install -e . && pytest -q && python -m hub.server
cd apps/analyzer   && pip install -r requirements.txt && pytest -q
cd apps/generator  && pytest -q && python -m generator
```

## Deploy

Each app has its own Dockerfile and may be deployed separately; `render.yaml` at the
root describes all four services so one file answers «what runs where».

## A note on the merge

Nothing was dropped. The five source repositories still exist and still build; this
one is where a change to a shared rule is made once instead of twice.
