"""Count what the model calls cost: calls, characters, and tokens when the endpoint reports them.

The analog of Vishap's `llm/_observe.py`. `collect()` opens a counter for the current thread of work; every
model call made inside it adds to the counter, so the pipeline can say how much each stage used.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class Usage:
    calls: int = 0
    chars_in: int = 0
    chars_out: int = 0
    tokens_in: int = 0
    tokens_out: int = 0

    def to_dict(self) -> dict:
        return {"calls": self.calls, "chars_in": self.chars_in, "chars_out": self.chars_out,
                "tokens_in": self.tokens_in, "tokens_out": self.tokens_out}

    def add(self, other: "Usage") -> None:
        self.calls += other.calls
        self.chars_in += other.chars_in
        self.chars_out += other.chars_out
        self.tokens_in += other.tokens_in
        self.tokens_out += other.tokens_out


_current: ContextVar[Usage | None] = ContextVar("llm_usage", default=None)


@contextmanager
def collect():
    """Count the model calls made inside the block."""
    usage = Usage()
    token = _current.set(usage)
    try:
        yield usage
    finally:
        _current.reset(token)


def observe_llm_result(messages: list[dict], answer: str, tokens_in: int = 0, tokens_out: int = 0) -> None:
    """Add one model call to the open counter, if there is one."""
    usage = _current.get()
    if usage is None:
        return
    usage.calls += 1
    usage.chars_in += sum(len(str(m.get("content", ""))) for m in messages)
    usage.chars_out += len(answer)
    usage.tokens_in += tokens_in
    usage.tokens_out += tokens_out
