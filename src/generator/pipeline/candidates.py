"""Best-of-N: several answers from the model, Verify picks.

The analog of Vishap's USC (several samples, take the most consistent). A vote shows what the samples agree on,
not what is right, so here the judge is the run: every candidate goes through Build's checks and Verify, and the
one with the most proof wins. Ties go to the lowest number, so the choice is repeatable. It costs N times the
tokens of one Build; `usage` shows it.

The candidates are only as different as the model's sampling makes them: with temperature 0 they are the same
answer N times (the CLI refuses `--repro` together with more than one candidate).
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from generator.pipeline.build import BuildCheck
from generator.pipeline.verdict import VerifyResult

RANK = {"passed": 2, "needs_verification": 1, "failed": 0}


@dataclass
class Candidate:
    index: int
    files: dict | None = None
    check: BuildCheck | None = None
    verify: VerifyResult | None = None
    error: str = ""

    @property
    def score(self) -> tuple:
        """Higher is better: build clean, then verdict, then how many requirements are proven."""
        if self.verify is None or self.check is None:
            return (-1, -1, -1)
        return (int(self.check.ok), RANK.get(self.verify.code_verdict, 0), self.verify.passed)


def pick_best(candidates: list[Candidate]) -> Candidate | None:
    """The best scored candidate; the lowest index among equals. None when no candidate produced files."""
    usable = [c for c in candidates if c.files is not None]
    if not usable:
        return None
    best = max(c.score for c in usable)
    return next(c for c in usable if c.score == best)


def summarize(candidates: list[Candidate], chosen: Candidate | None) -> list[dict]:
    rows = []
    for c in candidates:
        row = {"index": c.index, "chosen": c is chosen, "error": c.error}
        if c.verify is not None and c.check is not None:
            row.update(build_ok=c.check.ok, verdict=c.verify.code_verdict, passed=c.verify.passed,
                       requirements=len(c.verify.requirements))
        rows.append(row)
    return rows


def generate_all(n: int, make: Callable[[int], tuple[dict, BuildCheck]], workers: int) -> list[Candidate]:
    """Run `make(i)` for i in 0..n-1, `workers` at a time; a failing candidate is kept with its error."""
    def one(i: int) -> Candidate:
        try:
            files, check = make(i)
        except Exception as e:      # the model errors the caller cares about; the caller decides if all failed
            return Candidate(i, error=f"{type(e).__name__}: {e}")
        return Candidate(i, files=files, check=check)

    if workers <= 1 or n == 1:
        return [one(i) for i in range(n)]
    ctx = contextvars.copy_context()      # each thread counts into the same usage as the caller
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vg-cand") as pool:
        return list(pool.map(lambda i: ctx.copy().run(one, i), range(n)))
