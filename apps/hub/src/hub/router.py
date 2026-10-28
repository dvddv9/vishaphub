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
    "analyse": (Stage.ANALYSER,),
    "generate": (Stage.GENERATOR,),
    "validate": (Stage.VALIDATOR,),
    "generate+analyse": (Stage.GENERATOR, Stage.ANALYSER),
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
        return Plan(
            stages=stages,
            iterations=1,
            partial=True,
            note=f"only {stages[0].value} — the result is not verified by the other stages",
        )

    iterations = max(1, min(int(iterations), MAX_ITERATIONS))
    note = "" if iterations == 1 else f"{iterations} passes; stop early if the verdict stops improving"
    return Plan(stages=stages, iterations=iterations, partial=len(stages) < len(CANONICAL_ORDER), note=note)
