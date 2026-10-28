"""What the model calls cost.

The analog of Vishap's `pipeline/cost.py`. Prices are not invented here: set your provider's prices in USD per
1M tokens with GENERATOR_PRICE_IN and GENERATOR_PRICE_OUT, otherwise the cost is reported as 0.0 and only the
token counts are real. Tokens are counted only when the endpoint reports them.
"""

from __future__ import annotations

import os


def prices() -> tuple[float, float]:
    """(USD per 1M input tokens, USD per 1M output tokens) from the environment; 0.0 when unset."""
    def one(name: str) -> float:
        try:
            return max(0.0, float(os.environ.get(name, "0") or 0))
        except ValueError:
            return 0.0
    return one("GENERATOR_PRICE_IN"), one("GENERATOR_PRICE_OUT")


def prices_set() -> bool:
    """True when at least one price is set, so a cost of 0.0 means free and not unknown."""
    return any(p > 0 for p in prices())


def estimate_cost(tokens_in: int, tokens_out: int, price: tuple[float, float] | None = None) -> float:
    """Cost in USD, rounded to 6 decimals."""
    p_in, p_out = price if price is not None else prices()
    return round((tokens_in * p_in + tokens_out * p_out) / 1_000_000, 6)


def sum_stage_costs(stages: list[dict]) -> float:
    """Sum `cost_usd` over the stage records; anything that is not a dict is skipped."""
    return round(sum(s.get("cost_usd", 0.0) for s in stages if isinstance(s, dict)), 6)
