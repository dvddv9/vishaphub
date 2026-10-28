"""STRICT: refuse when too much of the key data is missing.

The analog of Vishap's `[STRICT]` mode and `STRICT_MISSING_PCT`. Off by default; `--strict` or
`quality_gate.strict_missing_pct` turns it on. Counts the key fields a run needs, not every optional one, and says
which are missing, so the answer is "add these", not "no".
"""

from __future__ import annotations

from generator.tools.spec import Spec

COMMON = ("target", "kind", "output", "inputs", "outputs", "must_never")
HTTP_ONLY = ("caller", "route")


def key_fields(spec: Spec) -> tuple[str, ...]:
    return COMMON + (HTTP_ONLY if spec.data.get("kind") == "http-endpoint" else ())


def missing_key_data(spec: Spec) -> tuple[list[str], float]:
    """(names of the missing key fields, their share of the key fields in percent)."""
    fields = key_fields(spec)
    missing = []
    for f in fields:
        value = spec.items.get(f) if f in ("inputs", "outputs", "must_never") else spec.data.get(f)
        if not value:
            missing.append(f)
    return missing, round(100.0 * len(missing) / len(fields), 1)


def strict_message(spec: Spec, limit: float | None) -> str | None:
    """The refusal text, or None when strict is off or enough is given."""
    if limit is None:
        return None
    missing, pct = missing_key_data(spec)
    if pct > limit:
        return f"Cannot answer reliably. Missing: {', '.join(missing)} ({pct:g}% of the key data, limit {limit:g}%)"
    return None
