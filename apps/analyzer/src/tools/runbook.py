# -*- coding: utf-8 -*-
"""P2-9 Runbook Generation: incident response steps per CWE.

Extends audit trail with structured runbook
(immediate / short_term / long_term / escalation).

Architecture:
    patterns.py  -> RUNBOOKS (data)
    runbook.py   -> generate_runbook(), enrich_runbook() (logic)

Deterministic: dict-lookup only, no LLM.
Fail-open: returns {} on error.
Backward compatible: adds new fields, does not mutate input.
"""
from src.tools.patterns import RUNBOOKS


def generate_runbook(cwe_ids: list[str]) -> dict:
    """Generate runbook for CWE IDs.

    Args:
        cwe_ids: e.g. ["CWE-89", "CWE-79"]

    Returns:
        {"CWE-89": {"title": ..., "severity": ...,
                    "immediate": [...], "short_term": [...],
                    "long_term": [...], "escalation": "..."},
         ...}
        Empty dict if no matches.
    """
    if not cwe_ids:
        return {}

    try:
        cwe_iter = list(cwe_ids)
    except Exception:
        return {}

    result: dict[str, dict] = {}

    for cwe in cwe_iter:
        entry = RUNBOOKS.get(cwe)
        if not entry:
            continue
        # Return a deep-ish copy to avoid mutation of the source dict
        result[cwe] = {
            "title": entry.get("title", ""),
            "severity": entry.get("severity", ""),
            "immediate": list(entry.get("immediate", [])),
            "short_term": list(entry.get("short_term", [])),
            "long_term": list(entry.get("long_term", [])),
            "escalation": entry.get("escalation", ""),
        }

    return result


def enrich_runbook(cwe_ids: list[str]) -> dict:
    """Enrich audit with runbook (backward-compatible).

    Does NOT mutate input.

    Args:
        cwe_ids: e.g. ["CWE-89"]

    Returns:
        {
            "runbook": {...},              # CWE -> runbook dict
            "runbook_cwes": [...],         # sorted CWE keys
            "runbook_steps_count": int,    # total steps across all CWEs
        }
    """
    try:
        cwes_copy = list(cwe_ids) if cwe_ids else []
    except Exception:
        cwes_copy = []

    try:
        runbook = generate_runbook(cwes_copy)
    except Exception:
        runbook = {}

    steps_count = 0
    for entry in runbook.values():
        steps_count += (
            len(entry.get("immediate", []))
            + len(entry.get("short_term", []))
            + len(entry.get("long_term", []))
        )

    return {
        "runbook": runbook,
        "runbook_cwes": sorted(runbook.keys()),
        "runbook_steps_count": steps_count,
    }
