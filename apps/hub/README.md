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

## Modules

| Piece | What it does |
|---|---|
| `server.py` | `GET /` the page, `GET /health`, `POST /chat`, `POST /run`, `POST /speak` |
| `router.py` | intent → ordered plan; deterministic, no model |
| `pipeline.py` | executes the plan; the only path to a verdict |
| `proposal.py` | the only place that talks to a model; returns a proposal, never a verdict |
| `verdicts.py` | one ranking for the whole hub: SAFE/PASS, *_REVIEW, FAIL, EMERGENCY, ERROR |
| `local.py` | the validator's stages and the analyser's rules as functions, not URLs |
| `envelope.py` | the message shape and the trace |
| `chat.py` | the assistant that speaks to the client |
| `tts.py` | the greeting's voice (`en-US-ChristopherNeural`), synthesised where the voice lives |
| `cli.py` | `vishap-hub run --intent …` — the same `run_plan` as the HTTP face |

## Status

`0.1.0` — one path, 62 tests (`PYTHONPATH=src python -m pytest -q`).

Not built yet: the microphone on the page — the voice speaks, the page does not listen.
