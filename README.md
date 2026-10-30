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

- **Where a run lives.** In the memory of the one hub process: the last 200 runs (`VISHAP_HUB_RUNS_KEEP`), older ones are dropped, and a restart empties it. This is the anonymous mode. Team mode (below) keeps runs in Postgres instead; the database in `apps/analyzer` is a separate thing.
- **The file mirror.** Off unless `VISHAP_HUB_RUNS_FILE` is set. With it, runs are also written to that file and read back at start, and a run then lives until newer ones push it out or the file is deleted. Whether it is on for the live service is a setting of that service, not of this repository.
- **What is stored.** The result of the run, not the submitted code as such: the verdict, the steps, the findings, the summary, the patch the model proposed (which contains code derived from the submission) and a fingerprint (hashes of the input). Findings can quote lines of the submitted code. The model key a client sends is never stored.
- **Who can open it.** The browser that made it. The first `/run` hands that browser a random token in a cookie (30 days; `HttpOnly`, `SameSite=Lax`); an API client can send the same kind of token as `x-vishap-owner`. The store keeps only a hash of the token. `/api/runs` and `/runs` need a token (403 without one) and list only that token's runs. A run opened by id is a 404 for anyone else, the same 404 as a run that never existed. These are not accounts: clearing the cookie loses access to the runs, and two visitors who submit the same code get the same run id and can both open it. One run is public: the example the page offers under "Try with an example" (`apps/hub/src/hub/demo.py`).
- **How to delete.** In the anonymous mode there is no delete: restarting the service empties the memory (and with the file mirror on, delete the file too). Team mode has a real delete (below).
- **What each run cost.** Every kept run records the characters it was sent and the size of what came back (`cost`); tokens are not metered. All runs also draw on one budget for the whole process, `VISHAP_HUB_GLOBAL_RUNS_PER_DAY` (default 200) and `VISHAP_HUB_GLOBAL_CHARS_PER_DAY`, in a sliding day; when it is spent `/run` answers 429 and says why, and `/health` still answers. That budget is in memory too: a restart resets it, so it bounds one process's day, not a provider bill. Chat and voice have a per-address limit only.

The report page says the same in one line, taken from the store: `Kept in memory until the service restarts: the last 200 runs, older ones are dropped.`

## How good are the analyzer's rules

`apps/analyzer/tests/bench/labelled/` holds 106 labelled examples in 11 languages (Python, JavaScript, TypeScript, Java, C, C++, PHP, Go, Terraform, Kubernetes YAML, Dockerfile): 71 dangerous and 35 safe. Each has the findings it should produce (CWE and line) and a written reason for its label in `manifest.json`; the expectations were written from the code, not copied from the engine's output. `python -m tests.bench.labelled_score` scores the rule engine on them, and `--write` refreshes `labelled/RESULTS.md`: recall, false positives, language detection and time, per language and per criticality, in two modes (file name given, as an upload; and pasted without one, as the hub does).

**What this does not measure.** It runs the rules alone: no model, no network, no key, so it is free and repeatable. It says nothing about the quality of hub verdicts that used a model. There the model proposes and the rules decide, and none of that is exercised here. A good number in this set is not a good hub, and a bad one is not a bad hub.

**Release blocker.** No example labelled critical may get SAFE (the rules found nothing at all), in either mode. `apps/analyzer/tests/test_bench_labelled.py` fails the analyzer CI job if one does, and it has no list of known failures to hide behind. The same file also fails when an example gets worse than the recorded results. Go has no language-specific rules, only the language-independent ones; the set includes it to show what that gives.

Four rules flag every call site on purpose (`subprocess` in Python, `ProcessBuilder` in Java, `system`/`execvp` in C, the shell functions in PHP), so safe code that calls them is counted as a false positive; the PHP rule skips a line that escapes its argument on that same line. The set counts them, and says so.

The first run found three critical examples (PHP shell calls, PHP `eval`, Go `sh -c`) that the rules called SAFE. Rules were written for them; `labelled/RESULTS.before-rules.md` keeps the first run, `RESULTS.md` compares, and the four examples the rules were written for or beside are marked `rules_written_after`, because they guard against regression but are not independent evidence of recall.

## Teams

Team mode is off until `VISHAP_HUB_DATABASE_URL` is set. Without it nothing below is loaded and the hub behaves as described above. With it, the runs of signed-in people are kept in Postgres, per team, and survive a restart. The driver is the hub's only dependency (`pip install "vishap-hub[postgres]"`), and the image has it.

- **Who owns the data.** A team owns its runs. A person belongs to one team and has one of three roles: `owner` (everything a member can, plus delete any run of the team and read the audit trail), `member` (run, read the team's runs, delete the ones they made) and `viewer` (read the team's runs, nothing that spends or removes). Everyone in a team reads all of the team's runs; nobody reads another team's.
- **How people get in.** An operator creates teams, people and keys with `python -m hub.admin`; there is no self-service. A key (`vhk_...`) is shown once when it is issued and only its SHA-256 is stored. Send it as `Authorization: Bearer vhk_...` (or `x-vishap-key`); a browser signs in at `/login`, which puts the key in an `HttpOnly` cookie. A wrong or revoked key is a 401 and never falls back to anonymous. `VISHAP_HUB_REQUIRE_KEY=1` makes `/run`, `/chat` and `/speak` refuse callers without a key (the setting for a pilot); without it anonymous callers behave as before, with the memory store.
- **How the teams are kept apart.** Twice. Every query filters on the team, and Postgres row-level security enforces the same on `runs` and `audit_log` for the role the server connects as (`vishap_hub_app`: not a superuser, cannot bypass RLS). That role cannot read `teams`, `users` or `api_keys` at all, and cannot change or delete an audit row. The tests check each layer on its own: with the code's filter removed isolation still holds, and with the policy removed the SQL-level test fails.
- **How long a run lives.** 30 days by default (`VISHAP_HUB_RETENTION_DAYS`), or the team's own value (`create-team --retention-days`). An expired run is unreadable at once and is deleted by a timer (`VISHAP_HUB_PURGE_MINUTES`, default 60) or by `purge-expired`. Running the same code again renews it. The report page says: `Kept in your team's database for 30 days from the run; an owner, or the person who made it, can delete it earlier.`
- **How to delete.** `DELETE /api/runs/<id>` removes the run row, with the result, findings and patch in it. What stays is one audit row (who, when, which id, no content) and the usage row for that request (sizes and token counts, with the link to the run removed). `python -m hub.admin purge-team <team> --yes` removes a team's runs, people and keys; its audit trail stays unless `--include-audit` is added.
- **Who looked.** Every create, read, list and delete by a signed-in person writes an audit row in the same transaction as the action: user, key, address, run id and outcome, refusals and misses included. An owner reads them at `GET /api/team/audit`. Expiry writes one row per team with a count. The address is that of the connection, so behind Render's proxy it is the proxy's. The audit trail is kept until an operator deletes it; it has no automatic expiry yet.
- **What a request may spend.** Every `/run`, `/chat` and `/speak` by a signed-in person takes one request out of three allowances before any work is done: the person's own, the team's, and the hub's for all teams together, each over a sliding 24 hours. A request that does not fit is refused with a 429 that says which allowance is spent, its limit and `Retry-After`; a refused request costs nothing and is audited (`quota.denied`). The reservation happens under a lock, so eight simultaneous requests against a limit of three let exactly three through, and a test does exactly that. A cached voice answer spends nothing and is not counted. The hub's allowance lives in the database, so a restart does not reset it; the anonymous budget above is separate and lives in memory.
- **The numbers are placeholders.** The defaults (50 runs a person and 200 a team a day, 100 and 500 for chat and for voice, 500, 1000 and 1000 for the hub as a whole, 20 million characters of run input) were not derived from anyone's costs: nothing here knows the price of a token or how many people the pilot has. Set them with `VISHAP_HUB_QUOTA_RUN_PER_USER` and `VISHAP_HUB_QUOTA_RUN_PER_TEAM` (also `CHAT`, `SPEAK`), `VISHAP_HUB_TEAMS_GLOBAL_RUN_PER_DAY` (also `CHAT`, `SPEAK`) and `VISHAP_HUB_TEAMS_GLOBAL_CHARS_PER_DAY`, or for one team with `python -m hub.admin set-quota <team> run --user 20 --team 100`. 0 means no limit.
- **Tokens: reported, and estimated.** The model's answer carries the token counts the provider reports. The hub records them, for a run that failed or was cut off as well because it was still paid for, in the usage ledger and in the run's `cost.tokens_measured`; `null` means the provider reported nothing, not that it was free. Beside it `cost.tokens_estimated` is characters divided by 4, labelled as an estimate. The two are never added together: `python -m hub.admin usage <team>` shows them in separate columns and says for how many requests anything was measured.
- **Alerts.** At 80% and at 100% of any of those allowances, and of the anonymous budget, the hub writes `ALERT ...` to its log and, if `VISHAP_HUB_ALERT_WEBHOOK` is set, posts `{"text": ...}` to it (the shape chat webhooks take). A dead webhook never delays a request. What was already announced is remembered by the process, so a restart can repeat an alert.
- **Operator.** `python -m hub.admin migrate | create-team | create-user | issue-key | revoke-key | disable-user | list | set-quota | usage | purge-expired | audit | purge-team`, with `VISHAP_HUB_ADMIN_DATABASE_URL` (the database owner). The server connects with `VISHAP_HUB_DATABASE_URL` (the `vishap_hub_app` role) and cannot migrate.
- **Not built.** Self-service signup, key rotation by the users themselves, SSO, sharing a single run outside its team, a cap on audit growth, connection pooling. The anonymous browser mode is memory-only and has no delete.

## What SAFE means

A verdict of **SAFE** from the hub's rules means exactly this: for the language of the text, the rules have been **measured** against an independently labelled blind set and passed the gates written down before the measurement; the scan could read **all** of the text (language recognised, no line cut, no part of the analysis quietly failed); and the rules **found nothing**. It is not a claim that the code has no vulnerabilities, and the rules do not look for every class of defect (authorization, business logic, dependencies, runtime configuration). Every response carries the `reason` and a `meaning` that says this.

Everything else is **REQUIRES_REVIEW**, with the reason: any finding of any severity (a critical one says so), a language that is not measured or failed its gates (*unknown coverage*), a text the scan could not read in full. A missing or unreadable `src/tools/quality.json` fails closed: nothing is SAFE. The decision is made in one place, `apps/analyzer/src/tools/safe_gate.py`.

SAFE is currently issued for: no language.

The gates, the sampling and the model-mode gates were committed before any example was fetched (`apps/analyzer/tests/bench/blind_public/CRITERION.md`, `SAMPLING.md`); the 402 examples come from three sources that label their own code (OWASP Benchmark for Java, DVWA for PHP, Bandit's examples for Python), are pinned by commit and SHA-256 and are not copied into this repository. The first run, kept untouched as `RESULTS.first-run.md`, found the rules alone calling SAFE 101 of 132 dangerous Java examples (12 of 24 critical), 29 of 38 PHP (8 of 10 critical) and 44 of 76 Python (15 of 24 critical), when the file name is given; and pasted without a name the engine reads Java as Python and PHP as unknown, which is what the hub sees. So the answer today is that none of it may be called SAFE. JavaScript, TypeScript, Go, C, C++, Terraform, YAML and Dockerfile have no blind set and are unmeasured. PHP (19 safe examples, one of them an empty file in its source) and Python (5) are below the registered minimum of 20.

**The hub's verdicts with a model are measured separately and have not been.** `python -m tests.bench.blind_public.model_eval` runs the same sample three times per example through the real model; it spends the key's money, needs `--confirm-spend`, and `--estimate` prints the size (about 372 calls and roughly 340 thousand input tokens by the characters / 4 estimate; no price, because nothing here knows the tariff). Until its result is committed the hub issues no SAFE with a model, in any language. A person who is not the author must also label a small sample of the team's real code (or an anonymised stand-in) for each language the team uses; `python -m tests.bench.blind_public.blind_score --human labels.csv --dir <folder>` scores it with the same code.

**Until then a pilot should use synthetic or anonymised examples.** What the hub says is a list of reasons to look, not an assurance.

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
