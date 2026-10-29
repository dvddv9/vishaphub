# VishapHub

One repository, one vocabulary, four pieces that used to be five repositories and
were slowly growing apart.

```
apps/
  analyzer/    the security analyst (FastAPI + Next.js UI)
  generator/   spec-to-code generator that proves its output
  hub/         runs the pipeline; the validator's six stages and the analyser's rules run inside it as libraries — live: vishap-hub.onrender.com
  validator/   does the code match the promise (six stages)
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
root describes the one service that runs in production: the hub image, with the validator and the analyser's rules inside it.

## A note on the merge

Nothing was dropped. The five source repositories still exist and still build; this
one is where a change to a shared rule is made once instead of twice.

## Known gaps

- **Tenant isolation (row-level security) is not tested anywhere.** The RLS tests in `apps/analyzer/tests/test_rls.py` skip themselves: the test database role is a superuser, which PostgreSQL exempts from RLS, and no RLS policy exists in the test database (one test reports `RLS policy not found`). Against a live Postgres, 27 of the 30 tests in the Postgres-backed files pass and these 3 skip, so a green run says nothing about isolation. To close it: create the policies in the test database and connect as the non-superuser `vishap_app` role.
- **The sandbox tests are skipped outside Linux.** Three tests in `apps/analyzer/tests/test_scan_toolkit.py` need `bubblewrap`, one needs symlinks; CI does not install bubblewrap.
- **Secrets are checked on the working tree only.** The `secrets` CI job runs gitleaks (`gitleaks detect --no-git`, policy in `.gitleaks.toml`) over the checked-out files. `--no-git` does not look at the past, so a secret that was committed and later removed is not found: the history is not scanned.
