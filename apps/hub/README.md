# VishapHub

The layer that carries a request between the client and three jobs:
**generator** (code from a spec), **validator** (does the code match the promise),
**analyser** (is it safe).

The hub does not decide the verdict. It routes, keeps the session, and speaks to the
client — the verdict belongs to the rules that produced it.

## One path

There used to be two mechanisms: a routed pipeline of stages, and a single-pass run that
asked the model once and glued the answers together. They ranked verdicts with two
different tables and could disagree about the same material. Now there is one:

```
POST /run  →  router (what was asked)  →  run_plan
                                          ├── generator  : the model proposes — a patch, findings, questions, proof
                                          ├── validator  : six stages on the patch that was proposed
                                          └── analyser   : patterns on the material AND on the proposed code
                                         → verdicts.py: the strictest verdict wins
```

Three rules hold the whole thing together:

- **the model proposes, the rules decide.** The model's own verdict is a recommendation:
  merged by rank, it can make an answer stricter, never softer. «Looks safe» cannot lift
  a failing test; a model that smells danger can raise the alarm.
- **generated code is checked like any other code.** The patch is written to a temp
  directory and given to the validator and the analyser — the hub does not take the
  author's word for its own output.
- **nothing ran is not a pass.** An empty plan, a missing stage verdict, a crashed stage,
  a missing key — all end in `ERROR`, and `ok` is true only when the verdict is safe.

## The planner

`router.py` is deterministic and has no model inside:

| Intent | Stages |
|---|---|
| `ask` | generator (the model answers; nothing is checked) |
| `analyse` | analyser |
| `generate` | generator |
| `validate` | validator |
| `generate+validate` | generator → validator |
| `validate+analyse` | validator → analyser |
| `generate+validate+analyse` | generator → validator → analyser |
| `review` | generator (the model reads the material) + analyser (the rules check it) |

`POST /run` infers the intent when the client does not name one: spec + material means
the full route, spec alone means generate and validate, a question alone means ask, material
alone means analyse (the rules, free, no key needed), and **material with a question means
review** - the model reads the material and answers the question, the rules check the same
material, and the stricter verdict wins. The model can raise a verdict and add findings (marked
`source: model`, apart from the rules' own); it can never remove what the rules found, and a
model's "safe" does not make unmeasured rules safe. Review needs a model key (the caller's
`api_key`, or one the operator set); without one the rules still answer and the run says that the
question was not put to a model. If the key is rejected, a review is still the rules' answer, with
the missing model reading named in `not_checked`; generation, which cannot happen without a model, is
still an error. An explicit `intent` always wins: `{"intent": "review"}` with no question asks the
model for a security review.

The two readers find different things, and the same thing in different words (`CWE-89` and
`sqli-fstring`), so the findings are joined, not stacked: a model finding and a rules finding that name
the same class of defect within three lines are one finding with `seen_by: ["rules", "model"]` (the
model's explanation, the rules' id and fix, the stricter severity); an unpaired one stays and says who
saw it alone. `agreement` counts `both`, `model_only`, `rules_only` and `in_patch` (the rules' findings
about the model's own patch, a different question). Nothing is ever dropped by this.

Rules that matter:

- **order is fixed**: generation, validation, security — dangerous code does not travel further;
- **iterations** capped at 3, and only for multi-stage routes; stop early when the verdict stops improving;
- **the generator runs once** — later passes re-check the same patch instead of paying the model again;
- **partial runs are marked**: a single stage returns `partial: true` with a note, so the client never reads «done» where «not verified» is true.

## The envelope

`envelope.py` — one message shape for every hop:

| Field | Why |
|---|---|
| `sender` / `recipient` | who talks to whom, checked against a fixed participant list |
| `kind` | question, answer, report, patch, verdict |
| `session_id` | one thread for the whole process |
| `payload` | the report or the code |
| `trace` | append-only: `hop()` returns a copy, the past is never rewritten |

## The assistant

`chat.py` and `prompt/vishap.md` — the business version of the persona: tone and
discipline without anything personal. It never gives a verdict, never re-audits
security, never asks more than three questions, and tells the client the truth about a
missing key. Without a key it still answers, from a local script: a page that says
nothing is worse than a page that says «bring a key».

## Doors

| Door | What it does | Costs | Ceiling |
|---|---|---|---|
| `GET /` | the page: talk, paste, run, read the report | nothing | — |
| `GET /health` | liveness for the platform | nothing | — |
| `POST /chat` | the assistant answers | a model call on the caller's key | 20 a minute per address |
| `POST /run` | one run, one verdict | a model call on the caller's key | 6 a minute per address |
| `POST /run/stream` | the same run as server-sent events | same | same |
| `POST /speak` | the voice | an outside synthesis service | 20 a minute, 600 characters, cached by the words |
| `GET /r/<id>` | a finished run as a page, owner only | nothing | — |
| `GET /api/runs` | your own recent runs, JSON | nothing | last 200 kept |
| `GET /api/runs/<id>.json` | one run, JSON, owner only | nothing | — |
| `GET /api/runs/<id>.sarif` | one run as SARIF 2.1.0, owner only | nothing | needs the analyser in the image, else `501` |
| `GET /styles.css`, `/app.js`, `/favicon.svg` | the page's own assets | nothing | `max-age=300`, must-revalidate |

One rule separates the two halves of the surface: **`/api/*` is JSON, everything else
is a page**. A wrong address under `/api` answers a JSON error; a wrong address
anywhere else answers an HTML page with a way back. That is why `/runs` is a list you
can read and `/api/runs` is the same list a program can parse.

A run belongs to whoever started it: a token in a cookie or in the owner header. Without
one the answer is `403`; for somebody else's run it is `404`, so the existence of that run
is not confirmed. The report page, the JSON and the SARIF export all share that check.

Every ceiling is an environment variable and `0` turns it off.

Per address, per minute: `VISHAP_HUB_RATE_RUN` (6), `VISHAP_HUB_RATE_CHAT` (20),
`VISHAP_HUB_RATE_SPEAK` (20).

The whole process, per sliding day — one bill, whoever asks:

| Variable | Default | What it bounds |
|---|---|---|
| `VISHAP_HUB_GLOBAL_RUNS_PER_DAY` | 200 | runs with a model call |
| `VISHAP_HUB_GLOBAL_CHARS_PER_DAY` | 5 000 000 | characters sent with runs |
| `VISHAP_HUB_GLOBAL_CHATS_PER_DAY` | 200 | chat messages that reach a model |
| `VISHAP_HUB_GLOBAL_CHAT_CHARS_PER_DAY` | 2 000 000 | characters sent by the chat |

The chat has its own ceiling on purpose: a conversation on the site must not close the door
for runs. Exhausted means `429` with `retry-after`, never a thinner answer.

Not money but threads: `VISHAP_HUB_MAX_CONCURRENT_RUNS` (4) is how many runs may be in flight at once; a run that
finds no free slot is answered `503` with `retry-after: 5` before it spends any budget. `VISHAP_HUB_READ_TIMEOUT` (30)
is how many seconds a connection may stay silent while the hub waits to read from it.

Also: `VISHAP_HUB_TTS_MAX_CHARS`, `VISHAP_HUB_TTS_CACHE`, `VISHAP_HUB_RUNS_KEEP`,
`VISHAP_HUB_RUNS_FILE` (a file to mirror the runs to, empty means memory only).

## Runs are stored, not believed

A finished run gets a fingerprint: the material, the spec, the plan, the verdict, the
steps, and the versions of the rules that judged it, hashed as canonical JSON. The id
is the first 16 hex characters of that hash, so the same run computed elsewhere gives
the same id — and `GET /r/<id>` shows the verdict, every step, every finding with its
source (`material` or `patch:<file>`), and **what was not checked**.

That last section is the point. «Safety was not checked: no analyser stage in this
plan» is the sentence that turns a result into a proof instead of an opinion. A run
that ends in ERROR is stored too: a failure is a result.

## The page

- **Try with an example** fills the material and runs it, so the first result is ten
  seconds away, not a decision about what to paste;
- the run is read as a stream: each stage lights up as it finishes, because a minute of
  silence reads as broken;
- **open the report** opens `/r/<id>` — a link that can be sent to someone who was not
  here;
- **not checked** is a tab of its own, in the same place as the findings;
- the microphone uses the browser's own speech recognition (Chrome and Edge; elsewhere
  the button says so), and the voice answers through `/speak`;
- English and Russian, switched in the header and remembered in the browser.

## How the page is built

- **one document, external assets.** `index.html` is markup only; `styles.css` and
  `app.js` are served from `/` with a cache header. Nothing is inline, so the Content
  Security Policy is `script-src 'self'; style-src 'self'` — no `unsafe-inline`;
- **semantics first.** `header` / `main` / `section` / `footer`, one `h1`, `h2` per
  panel, `role="log"` and `aria-live` on the conversation, `role="status"` on the
  verdict, a skip link, a visually hidden `label` for every field;
- **keyboard and focus.** every control is a real `button`, the file drop zone is
  `role="button" tabindex="0"` and answers Enter and Space, and `:focus-visible` draws a
  ring that the mouse never sees;
- **motion is optional.** `prefers-reduced-motion` turns off the pulses and the mic
  animation;
- **one breakpoint that matters.** under 900px the two columns become one; under 640px
  the stats stack, the report cells stack, type shrinks and fields sit at 16px so iOS
  does not zoom into them;
- **shareable.** `title`, `description`, `theme-color`, an SVG favicon, and a canonical
  link; a run report carries its own title and description.

## Modules

| Piece | What it does |
|---|---|
| `server.py` | the doors above, the limits, the static assets and their cache headers |
| `templates.py` | the run page, the runs page and the error page: one layout, one escape |
| `router.py` | intent → ordered plan; deterministic, no model |
| `pipeline.py` | executes the plan; the only path to a verdict |
| `proposal.py` | the only place that talks to a model; returns a proposal, never a verdict |
| `verdicts.py` | one ranking for the whole hub: SAFE/PASS, *_REVIEW, FAIL, EMERGENCY, ERROR |
| `fingerprint.py` | a run's identity: canonical hash over inputs, rules and verdict |
| `store.py` | the recent runs: bounded, thread-safe, optional file mirror |
| `limits.py` | the request budget per address and the voice cache |
| `local.py` | the validator's stages and the analyser's rules as functions, not URLs |
| `envelope.py` | the message shape and the trace |
| `chat.py` | the assistant that speaks to the client |
| `tts.py` | the voice (`en-US-AvaMultilingualNeural`, one voice for both languages), synthesised where the voice lives |
| `cli.py` | `vishap-hub run --intent …` — the same `run_plan` as the HTTP face |

## Status

`0.4.0` — teams, quotas, spend ceilings, SARIF, redaction before the model.
149 tests (`PYTHONPATH=src python -m pytest -q`), 54 of them need Postgres and skip without it.

Known gaps: the store lives in memory unless `VISHAP_HUB_RUNS_FILE` or the team store in
Postgres is configured (a free instance loses its runs on restart); there is no queue, so
two runs at once both wait for the model; card numbers are not redacted (no PAN pattern
in the analyser's list); and the SARIF export needs the analyser in the image.

The spend ceilings count in memory, per process: a restart or a redeploy resets them. They are a brake, not a
bill. For any model key the hub itself holds (`VISHAP_HUB_LLM_KEY`), set the real cap at the provider (a spend
limit in the Anthropic Console). A visitor's own key is the visitor's to cap.
