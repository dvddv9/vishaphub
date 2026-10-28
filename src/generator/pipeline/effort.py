"""How much work a run does: quick, standard or deep.

The analog of Vishap's depth levels (D0-D4) and of the orchestrator rule "complexity decides the stages". One name
sets the knobs together; any knob given on its own wins over the name. The numbers live here, in one place.

  quick     one repair round, no text check, no analyzer: a first look
  standard  what a run did before 0.6.0
  deep      three repair rounds, three candidates, the COVE check: for code that matters
"""

from __future__ import annotations

from dataclasses import dataclass

from generator.config import CANDIDATES_MAX, DEFAULT_REPAIRS, MAX_REPAIRS


@dataclass(frozen=True)
class Effort:
    name: str
    repairs: int
    candidates: int
    text_check: bool
    analyzer: bool
    cove: bool


EFFORTS = {
    "quick": Effort("quick", 1, 1, False, False, False),
    "standard": Effort("standard", DEFAULT_REPAIRS, 1, True, True, False),
    "deep": Effort("deep", 3, 3, True, True, True),
}


class EffortError(ValueError):
    pass


def resolve(name: str | None = None, *, repairs: int | None = None, candidates: int | None = None,
            text_check: bool | None = None, cove: bool | None = None) -> Effort:
    """The effort named (default standard) with any knob given on its own applied over it."""
    base = EFFORTS.get(name or "standard")
    if base is None:
        raise EffortError(f"effort must be one of: {', '.join(EFFORTS)}")
    out = Effort(base.name,
                 base.repairs if repairs is None else repairs,
                 base.candidates if candidates is None else candidates,
                 base.text_check if text_check is None else text_check,
                 base.analyzer,
                 base.cove if cove is None else cove)
    if not 0 <= out.repairs <= MAX_REPAIRS:
        raise EffortError(f"repairs must be from 0 to {MAX_REPAIRS}")
    if not 1 <= out.candidates <= CANDIDATES_MAX:
        raise EffortError(f"candidates must be from 1 to {CANDIDATES_MAX}")
    return out
