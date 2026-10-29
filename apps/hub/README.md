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

`POST /run` infers the intent when the client does not name one: spec + material means
the full route, spec alone means generate and validate, material alone means analyse, a
question alone means ask.

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
| `GET /r/<id>` | a finished run as a page | nothing | — |
| `GET /runs` | the recent runs | nothing | last 200 kept |

Every ceiling is an environment variable and `0` turns it off:
`VISHAP_HUB_RATE_RUN`, `VISHAP_HUB_RATE_CHAT`, `VISHAP_HUB_RATE_SPEAK`,
`VISHAP_HUB_TTS_MAX_CHARS`, `VISHAP_HUB_TTS_CACHE`, `VISHAP_HUB_RUNS_KEEP`,
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

## Modules

| Piece | What it does |
|---|---|
| `server.py` | the five doors above, the limits, the run page |
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
| `tts.py` | the greeting's voice (`en-US-ChristopherNeural`), synthesised where the voice lives |
| `cli.py` | `vishap-hub run --intent …` — the same `run_plan` as the HTTP face |

## Status

`0.3.0` — one path, 78 tests (`PYTHONPATH=src python -m pytest -q`).

Known gaps: the store lives in memory unless `VISHAP_HUB_RUNS_FILE` is set (a free
instance loses its runs on restart), and there is no queue: two runs at once both wait
for the model.
