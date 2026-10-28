# VishapHub

The layer that carries a request between the client and three services:
**generator** (code from a spec), **validator** (does the code match the promise),
**analyser** (is it safe).

The hub does not decide the verdict. It routes, keeps the session, and speaks to the
client — the verdict belongs to the pipeline that produced it.

## Two pieces so far

**`envelope.py`** — one message shape for every hop:

| Field | Why |
|---|---|
| `sender` / `recipient` | who talks to whom, checked against a fixed participant list |
| `kind` | question, answer, report, patch, verdict |
| `session_id` | one thread for the whole process |
| `payload` | the report or the code |
| `trace` | append-only: `hop()` returns a copy, the past is never rewritten |

**`router.py`** — deterministic planning, no model inside:

| Intent | Stages |
|---|---|
| `analyse` | analyser |
| `generate` | generator |
| `validate` | validator |
| `generate+validate` | generator → validator |
| `validate+analyse` | validator → analyser |
| `generate+validate+analyse` | generator → validator → analyser |

Rules that matter:

- **order is fixed**: generation, validation, security — dangerous code does not travel further;
- **iterations** capped at 3, and only for multi-stage routes; stop early when the verdict stops improving;
- **partial runs are marked**: a single stage returns `partial: true` with a note, so the client never reads «done» where «not verified» is true.

## The assistant

`prompt/vishap.md` — the business version of the persona: tone and discipline without
anything personal. It never gives a verdict, never re-audits security, never asks more
than three questions, and tells the client the truth about a missing key.

## Status

`0.1.0` — envelope and router work; the transport to the three services is next.
Tests are deliberately left for the end of the build.
