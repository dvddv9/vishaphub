<img width="3327" height="1683" alt="Снимок экрана3 2026-10-29 201505" src="https://github.com/user-attachments/assets/b2a21529-e613-4d23-9dc1-9590524f06c7" />


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

The hub's version is the one in `apps/hub/src/hub/version.py` (a test keeps `pyproject.toml` equal to it) and `/health` reports it; the repository has no git tags, so a deployed build is identified by its commit, not by a tag.

## A note on the merge

Nothing was dropped. The five source repositories still exist and still build; this
one is where a change to a shared rule is made once instead of twice.

## What happens to the data

- **Where a run lives.** In the memory of the one hub process: the last 200 runs (`VISHAP_HUB_RUNS_KEEP`), older ones are dropped, and a restart empties it. Postgres plays no part in the hub; the database in `apps/analyzer` is a separate thing.
- **The file mirror.** Off unless `VISHAP_HUB_RUNS_FILE` is set. With it, runs are also written to that file and read back at start, and a run then lives until newer ones push it out or the file is deleted. Whether it is on for the live service is a setting of that service, not of this repository.
- **What is stored.** The result of the run, not the submitted code as such: the verdict, the steps, the findings, the summary, the patch the model proposed (which contains code derived from the submission) and a fingerprint (hashes of the input). Findings can quote lines of the submitted code. The model key a client sends is never stored.
- **Who can open it.** The browser that made it. The first `/run` hands that browser a random token in a cookie (30 days; `HttpOnly`, `SameSite=Lax`); an API client can send the same kind of token as `x-vishap-owner`. The store keeps only a hash of the token. `/api/runs` and `/runs` need a token (403 without one) and list only that token's runs. A run opened by id is a 404 for anyone else, the same 404 as a run that never existed. These are not accounts: clearing the cookie loses access to the runs, and two visitors who submit the same code get the same run id and can both open it. One run is public: the example the page offers under "Try with an example" (`apps/hub/src/hub/demo.py`).
- **How to delete.** There is no delete. Restarting the service empties the memory (and with the file mirror on, delete the file too). Permanent deletion comes with a database, which is not built.
- **What each run cost.** Every kept run records the characters it was sent and the size of what came back (`cost`); tokens are not metered. All runs also draw on one budget for the whole process, `VISHAP_HUB_GLOBAL_RUNS_PER_DAY` (default 200) and `VISHAP_HUB_GLOBAL_CHARS_PER_DAY`, in a sliding day; when it is spent `/run` answers 429 and says why, and `/health` still answers. That budget is in memory too: a restart resets it, so it bounds one process's day, not a provider bill. Chat and voice have a per-address limit only.

The report page says the same in one line, taken from the store: `Kept in memory until the service restarts: the last 200 runs, older ones are dropped.`

## Known gaps

- **The sandbox tests skip outside Linux.** Three tests in `apps/analyzer/tests/test_scan_toolkit.py` need `bubblewrap` and one needs symlinks, so on a Windows machine they skip. In CI they must run: the job installs bubblewrap, probes it, and `.github/scripts/assert_no_skips.py` fails the build if any test in `test_rls`, `test_scan_toolkit` or the Postgres job-store tests was skipped.
- **Secrets in history are named, not hidden.** CI scans the whole history (`secrets-history`). Twelve old findings are test fixtures from before the monorepo (short `AKIA` sequences, a 27-character `sk_live_` string, a 75-character PEM block, the demo Terraform password); each is one exact fingerprint in `.gitleaksignore`, and the path allowlist in `.gitleaks.toml` names the five test files that hold fake credentials instead of allowing every file under `tests/`.
- **Tenant isolation is checked in CI, not on every developer machine.** `test_rls.py` builds a scratch database, runs the migrations and connects as `vishap_app` (NOSUPERUSER, NOBYPASSRLS); without `TEST_POSTGRES_URL` it skips, with it a missing policy or a role that bypasses RLS fails.

## Secrets live outside the project tree

Agents (Codex, Claude, any MCP client) open this folder as a project and can run
`shell` inside it. A `.env` in the tree is therefore a readable file, not a secret:
it is git-ignored, but ignored is not hidden.

- Keys belong in user environment variables (`setx VISHAP_LLM_KEY "..."`) or in a file
  outside the repository, loaded by the launcher — not in `apps/*/.env`.
- The repository keeps `.env.example` with placeholders and nothing else.
- `API_KEY_PEPPER` is checked at startup (`src/config.validate_secrets`): if
  `VISHAP_TENANT_KEYS` is on and the pepper is empty or still a placeholder from
  `.env.example`, the API refuses to start. A placeholder pepper makes every issued
  tenant key forgeable by anyone who read the example.
