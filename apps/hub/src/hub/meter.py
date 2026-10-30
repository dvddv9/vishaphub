"""Tokens the model provider actually reported, kept apart from any estimate.

A run makes its model call somewhere deep in the pipeline; the door that started the run wants the bill.
`metering()` opens a meter for the current request (a context variable, so concurrent requests never share
one), the code that makes a model call hands the provider's `usage` block to `record()`, and the door reads
the totals afterwards - also when the run failed, because a refused or truncated answer was still paid for.

Only what the provider reported is counted as measured. When it reports nothing the measured side is
None, not zero: zero would read as "free".
"""
from __future__ import annotations

import contextlib
import contextvars
import math
from dataclasses import dataclass

_current: contextvars.ContextVar[Meter | None] = contextvars.ContextVar("hub_meter", default=None)

#: the estimate: one token per this many characters. A rule of thumb, labelled as one wherever it is shown.
CHARS_PER_TOKEN = 4


@dataclass
class Meter:
    calls: int = 0
    measured_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0

    def add(self, usage: object) -> None:
        self.calls += 1
        if not isinstance(usage, dict):
            return
        tin = usage.get("input_tokens", usage.get("prompt_tokens"))
        tout = usage.get("output_tokens", usage.get("completion_tokens"))
        if isinstance(tin, int) and isinstance(tout, int):
            self.measured_calls += 1
            self.tokens_in += tin
            self.tokens_out += tout

    def measured(self) -> dict | None:
        """What the provider reported, or None when it reported nothing for any call."""
        if not self.measured_calls:
            return None
        return {"input": self.tokens_in, "output": self.tokens_out,
                "calls": self.calls, "calls_measured": self.measured_calls}


@contextlib.contextmanager
def metering():
    meter = Meter()
    token = _current.set(meter)
    try:
        yield meter
    finally:
        _current.reset(token)


def record(usage: object) -> None:
    """Called where a model answer arrives. A no-op outside a metered request."""
    meter = _current.get()
    if meter is not None:
        meter.add(usage)


def estimate(input_chars: int, result_chars: int) -> dict:
    """characters / 4. An estimate of the order of magnitude, not a count."""
    return {"input": math.ceil(max(0, input_chars) / CHARS_PER_TOKEN),
            "output": math.ceil(max(0, result_chars) / CHARS_PER_TOKEN),
            "basis": f"characters / {CHARS_PER_TOKEN}"}


def cost_of(meter: Meter | None, input_chars: int, result_chars: int) -> dict:
    """The cost block kept with a run: sizes, the provider's token counts, and the estimate - three separate things."""
    return {"input_chars": input_chars, "result_chars": result_chars,
            "tokens_measured": meter.measured() if meter else None,
            "tokens_estimated": estimate(input_chars, result_chars)}
