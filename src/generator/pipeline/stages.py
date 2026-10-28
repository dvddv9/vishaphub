"""The five stages: their order, their prompts, how a stage is timed, and how a model answer is read.

The analog of Vishap's `pipeline/stages.py`: a registry of the stages, one place where a model's JSON answer
is parsed (`parse_json_response`), and a clock that records, per stage, how long it took and what the model
calls cost (`StageClock`, Vishap's `_meta` of each stage).

Intake, Verify and Deliver have no prompt: they are deterministic code on purpose.
tests/test_prompts.py keeps this list and the prompts/ folder in step.

Unlike Vishap, a truncated JSON answer is NOT repaired: a file cut off in the middle is a wrong file,
and passing it on would turn a model failure into code that looks complete.
"""

from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass

from generator.llm._observe import Usage, collect
from generator.pipeline.cost import estimate_cost


@dataclass(frozen=True)
class Stage:
    key: str
    number: int
    title: str
    module: str
    prompts: tuple[str, ...] = ()


STAGES = (
    Stage("intake", 1, "Intake", "generator.pipeline.intake"),
    Stage("design", 2, "Design", "generator.pipeline.design", ("02_design_textcheck",)),
    Stage("build", 3, "Build", "generator.pipeline.generate", ("03_build", "03_build_repair")),
    Stage("verify", 4, "Verify", "generator.pipeline.verify"),
    Stage("deliver", 5, "Deliver", "generator.pipeline.deliver"),
)
BY_KEY = {s.key: s for s in STAGES}
SHARED_PROMPT = "00_rules"


def prompt_names() -> list[str]:
    return [SHARED_PROMPT] + [p for s in STAGES for p in s.prompts]


# ---------------------------------------------------------------- reading a model answer

FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n(.*)\n\s*```\s*$", re.DOTALL)


def parse_json_response(answer: str) -> dict:
    """The JSON object in a model's answer. A Markdown fence around it is tolerated.

    Raises ValueError with a short reason when the answer is not one JSON object.
    """
    text = answer.strip()
    fenced = FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ValueError(f"answer is not JSON: {e.msg} at line {e.lineno}") from None
    if not isinstance(data, dict):
        raise ValueError("answer must be one JSON object")
    return data


# ---------------------------------------------------------------- timing a stage

class StageClock:
    """Collects, per stage, the time spent and the model usage. One clock per run.

    A stage may be entered more than once (Build again for every repair round); the figures add up.
    """

    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}
        self._order: list[str] = []

    @contextmanager
    def stage(self, key: str):
        row = self._rows.get(key)
        if row is None:
            row = {"key": key, "title": BY_KEY[key].title, "runs": 0, "duration_s": 0.0,
                   "usage": Usage(), "ok": True, "error": ""}
            self._rows[key] = row
            self._order.append(key)
        started = time.perf_counter()
        with collect() as usage:
            try:
                yield usage
            except BaseException as e:
                row["ok"], row["error"] = False, f"{type(e).__name__}: {e}"[:200]
                raise
            finally:
                row["runs"] += 1
                row["duration_s"] += time.perf_counter() - started
                row["usage"].add(usage)

    def records(self) -> list[dict]:
        out = []
        for key in self._order:
            r = self._rows[key]
            u = r["usage"]
            out.append({"key": key, "title": r["title"], "runs": r["runs"],
                        "duration_s": round(r["duration_s"], 3), "ok": r["ok"], "error": r["error"],
                        "llm_calls": u.calls, "tokens_in": u.tokens_in, "tokens_out": u.tokens_out,
                        "cost_usd": estimate_cost(u.tokens_in, u.tokens_out)})
        return out
