"""A person's note on a finding: accepted, and why. It sits beside the finding and never changes the verdict.

The rules decide the verdict and the model can only raise it; a human saying "this one is fine here" is a third
thing, and it is kept as what it is: who, when and the reason, shown next to the finding in the report. The finding
is still listed, the verdict is still the one the checks gave, and the SARIF of the run still has it.

The marks live inside the run's own result (`result["accepted"]`, keyed by a short digest of the finding), so
there is no new table: a run that expires takes its marks with it, and a re-run of the same material keeps them.
"""
from __future__ import annotations

import hashlib

MAX_MARKS = 100
MAX_REASON = 300


def key_of(finding: dict) -> str:
    """A short, stable name for one finding of one run: its class, file, line and the start of its message."""
    basis = "|".join([
        str(finding.get("cwe") or finding.get("rule") or ""),
        str(finding.get("file") or ""),
        str(finding.get("line") or 0),
        str(finding.get("message") or "")[:120],
    ])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def _keys(result: dict) -> set[str]:
    return {key_of(f) for f in result.get("findings") or [] if isinstance(f, dict)}


def mark(result: dict, key: str, reason: object, by: str, at: str) -> dict:
    """The result with one more finding accepted. Raises ValueError, in words a person can read, when it cannot."""
    why = str(reason or "").strip() if isinstance(reason, str) else ""
    if not why:
        raise ValueError("a reason is required: say why this finding is accepted")
    if len(why) > MAX_REASON:
        raise ValueError(f"the reason is longer than {MAX_REASON} characters")
    if key not in _keys(result):
        raise ValueError("no such finding in this run")
    marks = dict(result.get("accepted") or {})
    if key not in marks and len(marks) >= MAX_MARKS:
        raise ValueError(f"a run keeps at most {MAX_MARKS} accepted findings")
    marks[key] = {"reason": why, "by": str(by)[:64], "at": str(at)}
    return {**result, "accepted": marks}


def unmark(result: dict, key: str) -> dict:
    marks = dict(result.get("accepted") or {})
    if key not in marks:
        raise ValueError("this finding is not marked as accepted")
    del marks[key]
    return {**result, "accepted": marks}


def decorate(result: dict) -> dict:
    """The result as it is shown: every finding carries its `key`, and `accepted` when a person marked it."""
    marks = result.get("accepted") or {}
    out = []
    for finding in result.get("findings") or []:
        if not isinstance(finding, dict):
            out.append(finding)
            continue
        key = key_of(finding)
        item = {**finding, "key": key}
        if key in marks:
            item["accepted"] = marks[key]
        out.append(item)
    return {**result, "findings": out}


def shown(record: dict) -> dict:
    """A stored record as it is served."""
    result = record.get("result")
    return {**record, "result": decorate(result)} if isinstance(result, dict) else record