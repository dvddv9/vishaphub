"""Routing: what the client asked for, and which services that implies.

The router is deterministic and has no model in it. The assistant (the Vishap
persona) may *talk* to the client, but the plan comes from this table — otherwise
the same request would route differently on different days.

Order is fixed: generation, then validation, then security. Dangerous code does not
travel further than the first stage that rejects it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Stage(str, Enum):
    GENERATOR = "generator"
    ANALYSER = "analyser"
    VALIDATOR = "validator"


ROUTES: dict[str, tuple[Stage, ...]] = {
    "ask": (Stage.GENERATOR,),
    "analyse": (Stage.ANALYSER,),
    "generate": (Stage.GENERATOR,),
    "validate": (Stage.VALIDATOR,),
    "generate+analyse": (Stage.GENERATOR, Stage.ANALYSER),
    # The model reads the material and the rules check it. Same two stages as generate+analyse, but its own
    # name, because the client's question is "look at my code", not "write me some".
    "review": (Stage.GENERATOR, Stage.ANALYSER),
    "generate+validate": (Stage.GENERATOR, Stage.VALIDATOR),
    "generate+validate+analyse": (Stage.GENERATOR, Stage.VALIDATOR, Stage.ANALYSER),
    "validate+analyse": (Stage.VALIDATOR, Stage.ANALYSER),
}

#: The only order the hub ever executes, regardless of how the request was written.
CANONICAL_ORDER = (Stage.GENERATOR, Stage.VALIDATOR, Stage.ANALYSER)

MAX_ITERATIONS = 3


class RouteError(ValueError):
    """The request cannot be routed without asking the client."""


@dataclass
class Plan:
    stages: tuple[Stage, ...]
    iterations: int = 1
    partial: bool = False
    note: str = ""
    #: A model that cannot answer is an error for a request that needs it (generate), and a missing second
    #: opinion for one that does not (review): the rules' answer is still an answer.
    model_optional: bool = False

    def as_dict(self) -> dict:
        return {
            "stages": [s.value for s in self.stages],
            "iterations": self.iterations,
            "partial": self.partial,
            "note": self.note,
        }


def plan_for(intent: str, iterations: int = 1) -> Plan:
    """Turn a client intent into an ordered plan.

    ``iterations`` is capped at MAX_ITERATIONS and only makes sense for the full
    cycle: asking for three passes of a single stage is just a slow way to do one.
    """
    key = (intent or "").strip().lower()
    if key not in ROUTES:
        raise RouteError(f"unknown intent: {intent!r}; ask the client which one they mean")

    requested = ROUTES[key]
    stages = tuple(s for s in CANONICAL_ORDER if s in requested)

    if len(stages) == 1:
        note = ("only the model answered; no rule checked the answer" if key == "ask"
                else f"only {stages[0].value} — the result is not verified by the other stages")
        return Plan(stages=stages, iterations=1, partial=True, note=note)

    if key == "review":
        return Plan(stages=stages, iterations=1, partial=True, model_optional=True,
                    note="the model read the material and the rules checked it, the stricter verdict wins; "
                         "no spec, so no validator")

    iterations = max(1, min(int(iterations), MAX_ITERATIONS))
    note = "" if iterations == 1 else f"{iterations} passes; stop early if the verdict stops improving"
    return Plan(stages=stages, iterations=iterations, partial=len(stages) < len(CANONICAL_ORDER), note=note)
