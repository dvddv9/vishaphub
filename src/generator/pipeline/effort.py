"""How much work a run does: quick, standard or deep.

The analog of Vishap's depth levels (D0-D4) and of the orchestrator rule "complexity decides the stages". One name
sets the knobs together; any knob given on its own wins over the name. The numbers live here, in one place.

  quick     one repair round, no text check, no analyzer, no mutation check: a first look
  standard  what a run did before 0.6.0, plus a mutation check of the tests (12 changes)
  deep      three repair rounds, three candidates, the COVE check, 30 mutants and a round that strengthens weak tests:
            for code that matters

GENERATOR_MUTANTS (a whole number, 0 turns the check off) replaces the number of mutants every effort would use;
the `mutants` knob given on its own still wins.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from generator.config import CANDIDATES_MAX, DEFAULT_REPAIRS, MAX_REPAIRS, MUTANTS_MAX


@dataclass(frozen=True)
class Effort:
    name: str
    repairs: int
    candidates: int
    text_check: bool
    analyzer: bool
    cove: bool
    mutants: int = 0            # changes made to the code to see if the tests notice (0: off)
    strengthen: bool = False    # one repair round that asks for tests which catch the surviving changes


EFFORTS = {
    "quick": Effort("quick", 1, 1, False, False, False, 0, False),
    "standard": Effort("standard", DEFAULT_REPAIRS, 1, True, True, False, 12, False),
    "deep": Effort("deep", 3, 3, True, True, True, 30, True),
}


class EffortError(ValueError):
    pass


def resolve(name: str | None = None, *, repairs: int | None = None, candidates: int | None = None,
            text_check: bool | None = None, cove: bool | None = None, mutants: int | None = None) -> Effort:
    """The effort named (default standard) with any knob given on its own applied over it."""
    base = EFFORTS.get(name or "standard")
    if base is None:
        raise EffortError(f"effort must be one of: {', '.join(EFFORTS)}")
    if mutants is None:
        raw = os.environ.get("GENERATOR_MUTANTS", "").strip()
        mutants = int(raw) if raw.isdigit() else base.mutants
    out = Effort(base.name,
                 base.repairs if repairs is None else repairs,
                 base.candidates if candidates is None else candidates,
                 base.text_check if text_check is None else text_check,
                 base.analyzer,
                 base.cove if cove is None else cove,
                 mutants, base.strengthen and mutants > 0)
    if not 0 <= out.repairs <= MAX_REPAIRS:
        raise EffortError(f"repairs must be from 0 to {MAX_REPAIRS}")
    if not 0 <= out.mutants <= MUTANTS_MAX:
        raise EffortError(f"mutants must be from 0 to {MUTANTS_MAX}")
    if not 1 <= out.candidates <= CANDIDATES_MAX:
        raise EffortError(f"candidates must be from 1 to {CANDIDATES_MAX}")
    return out
