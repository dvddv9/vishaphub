"""Questions for the author: what the spec would have to say so that the model need not guess.

Each gap is a place where the spec is silent or unclear. Where the model chose something on its own it left an
`# assumption:` comment; this module turns the gaps into questions and sets each beside the assumption that answers
it (the comment names the gap id). A person who answers the question in the spec removes the guess: the next run
has a requirement there, with a test and an attack. No model is called.
"""

from __future__ import annotations

import re

QUOTED = re.compile(r'^(?:\w+) says "(.+?)" but no requirement covers it')
GAP_ID = re.compile(r"\bG\d+\b")


def _question(gap) -> str:
    text = gap.text
    m = QUOTED.match(text)
    if m:
        return f'The text says "{m.group(1)}". Which requirement should say this, or may the generator leave it out?'
    if gap.type == "missing_input":
        return f"The spec does not say: {text}. What should it say?"
    if gap.type == "contradiction":
        return f"Two parts of the spec disagree: {text}. Which one holds?"
    if gap.type == "secret":
        return "A secret is written in the spec. Replace it: from which setting or environment variable should the code read it?"
    if gap.type == "injection":
        return f"{text}. Remove it, or say what you meant in plain requirements."
    if gap.type == "reminder":
        return f"{text} If yes, add it to the spec as a requirement."
    return f"{text}. Is that what you want, or should the spec say otherwise?"


def questions_for(gaps, assumptions) -> list[dict]:
    """[{gap, severity, question, assumed}]: `assumed` is the model's own answer when it left one for this gap."""
    by_gap: dict[str, list[dict]] = {}
    for a in assumptions or ():
        for gid in GAP_ID.findall(a["text"]):
            by_gap.setdefault(gid, []).append(a)
    out = []
    for g in gaps:
        row = {"gap": g.id, "severity": g.severity, "question": _question(g), "assumed": ""}
        if g.id in by_gap:
            first = by_gap[g.id][0]
            row["assumed"] = f"{first['text']} ({first['file']}:{first['line']})"
        out.append(row)
    return out
