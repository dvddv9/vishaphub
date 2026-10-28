"""Baseline of accepted gaps: fingerprint based, stable across re-runs.

The analog of Vishap's `tools/baseline.py`. A critical gap blocks the gate. When the owner decides to live
with one on purpose, `vishap-generator baseline spec.yaml` records its fingerprint; from then on the gate lists
it as accepted instead of blocking. The fingerprint is made of the gap's type and text, not its number or line,
so it survives re-numbering and edits elsewhere in the spec.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

DEFAULT_PATH = Path(".vishap") / "baseline.json"


def compute_fingerprint(gap) -> str:
    text = " ".join(str(gap.text).split()).lower()
    return hashlib.sha256(f"{gap.type}|{text}".encode("utf-8")).hexdigest()[:16]


def save_baseline(gaps, path: str | Path) -> list[str]:
    """Write the fingerprints of `gaps`; returns them."""
    prints = sorted({compute_fingerprint(g) for g in gaps})
    items = [{"fingerprint": compute_fingerprint(g), "type": g.type, "text": g.text} for g in gaps]
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 1, "accepted": items}, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")
    return prints


def load_baseline(path: str | Path) -> frozenset[str]:
    """The accepted fingerprints; an absent or unreadable file accepts nothing."""
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return frozenset(str(i["fingerprint"]) for i in data.get("accepted", []))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return frozenset()


def filter_new(gaps, accepted: frozenset[str]) -> tuple[list, list]:
    """(gaps still open, gaps accepted by the baseline)."""
    new, old = [], []
    for g in gaps:
        (old if compute_fingerprint(g) in accepted else new).append(g)
    return new, old
