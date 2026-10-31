"""How well the rules are measured for the language a client just analysed.

The hub has no list of "supported languages" that someone typed in. What it can say about a language is what a
labelled benchmark measured: examples with a label (dangerous or safe), an expected finding and a reason. The
counts come from `data/language_evidence.json`, which `scripts/language_evidence.py` copies from the
analyzer's benchmark and a test keeps current.

Three adequacies, by rule and not by opinion:

* `measured`: at least MIN_DANGEROUS dangerous and MIN_SAFE safe examples. Enough to see a miss and a false alarm;
  still a small set, never a guarantee about any real code.
* `thin`: some labelled examples, fewer than that. The counts are shown as counts: a percentage of three examples
  is not a rate.
* `none`: no labelled example. Nothing is known about how often the rules miss in this language.

The hub sends only text to the rules (no file name), so the numbers used are the benchmark's `pasted` mode.
A language that the engine has rules for but no labelled set must be named in EXEMPT, with the reason: a new
language cannot get rules without data or an explicit, visible exemption (see the gate test).
"""
from __future__ import annotations

import json
import os

MIN_DANGEROUS = 10
MIN_SAFE = 5
MODE = "pasted"

#: Languages the engine has rules for but the benchmark has no labelled set for, by decision, with the reason.
EXEMPT = {"log": "log lines are checked for attack patterns, not read as code; there is no labelled set for them yet"}

_PATH = os.path.join(os.path.dirname(__file__), "data", "language_evidence.json")
_CACHE: dict | None = None


def data() -> dict:
    global _CACHE
    if _CACHE is None:
        try:
            with open(_PATH, encoding="utf-8") as fh:
                _CACHE = json.load(fh)
        except (OSError, json.JSONDecodeError):
            _CACHE = {"languages": {}, "source": {}}
    return _CACHE


UNKNOWN = ("the language was not recognised from the text alone (the hub sends text without a file name), "
           "so only the language-independent rules ran")


def known() -> list[str]:
    return sorted(set(data().get("languages", {})) | set(EXEMPT) | {"unknown"})


def evidence_for(language: str) -> dict:
    """What was measured for `language`: counts, and the adequacy those counts earn. Deterministic."""
    lang = str(language or "unknown")
    row = (data().get("languages") or {}).get(lang)
    if not row:
        why = UNKNOWN if lang == "unknown" else (EXEMPT.get(lang) or "no labelled example exists for this language")
        return {"language": lang, "adequacy": "none", "reason": why, "mode": MODE}
    m = row.get(MODE) or {}
    dangerous, safe = int(m.get("dangerous_examples", 0)), int(m.get("safe_examples", 0))
    expected, hit = int(m.get("expected_findings", 0)), int(m.get("hit_findings", 0))
    adequacy = "measured" if dangerous >= MIN_DANGEROUS and safe >= MIN_SAFE else "thin"
    return {"language": lang, "adequacy": adequacy, "mode": MODE,
            "dangerous_examples": dangerous, "safe_examples": safe,
            "expected_findings": expected, "hit_findings": hit,
            "recall_percent": round(100 * hit / expected) if expected else None,
            "dangerous_got_safe": int(m.get("dangerous_got_safe", 0)),
            "critical_got_safe": int(m.get("critical_got_safe", 0)),
            "safe_flagged": int(m.get("safe_flagged", 0)),
            "not_independent_examples": int(row.get("not_independent_examples", 0))}


def sentence(ev: dict) -> str:
    """One honest line for a page or an export."""
    lang = ev.get("language")
    if ev.get("adequacy") == "none":
        return f"{lang}: not measured ({ev.get('reason')}); nothing is known about how often the rules miss"
    body = (f"{ev['dangerous_examples']} dangerous and {ev['safe_examples']} safe labelled example(s); the rules "
            f"hit {ev['hit_findings']} of {ev['expected_findings']} expected findings, "
            f"{ev['dangerous_got_safe']} dangerous example(s) got SAFE, {ev['safe_flagged']} safe example(s) were flagged")
    if ev["adequacy"] == "thin":
        return (f"{lang}: thin evidence ({body}); fewer than {MIN_DANGEROUS} dangerous or {MIN_SAFE} safe examples, "
                "so these are counts, not rates")
    return f"{lang}: measured ({body}); still a small set, not a guarantee about your code"


def table() -> dict:
    """Everything `/api/languages` says."""
    return {"schema": "vishap.languages/1", "mode": MODE,
            "thresholds": {"measured_needs_dangerous": MIN_DANGEROUS, "measured_needs_safe": MIN_SAFE},
            "source": data().get("source", {}), "exempt": EXEMPT,
            "languages": [evidence_for(lang) for lang in known()]}