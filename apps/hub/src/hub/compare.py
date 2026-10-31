"""Two runs side by side: what changed between them, and why that may be.

A second run of the same material after a rule update, a patch that was checked after the run that proposed it,
two runs of different material: they are all one question, "what is different?", and the answer says which
kind of difference it is. The input fingerprints (material, spec, files) tell whether the two runs looked at the
same thing; the rule versions and the sandbox profile say whether the same judge did.

Findings are compared by rule, severity and message, never by line: a line number moves when code above it
changes, and a moved finding is not a new one.
"""
from __future__ import annotations

from collections import Counter

from .verdicts import rank


def _result(record: dict) -> dict:
    return record.get("result") if isinstance(record.get("result"), dict) else record


def _body(result: dict) -> dict:
    return (result.get("fingerprint") or {}).get("body") or {}


def _finding_key(f: dict) -> tuple:
    return (str(f.get("rule") or ""), str(f.get("severity") or ""), str(f.get("message") or ""))


def _listed(counter: Counter) -> list[dict]:
    return [{"rule": r, "severity": s, "message": m, "count": n} for (r, s, m), n in sorted(counter.items())]


def _pair(a, b) -> dict:
    return {"a": a, "b": b, "changed": a != b}


def diff(a: dict, b: dict) -> dict:
    ra, rb = _result(a), _result(b)
    ba, bb = _body(ra), _body(rb)
    fa, fb = ra.get("fingerprint") or {}, rb.get("fingerprint") or {}
    same_input = bool(ba and bb) and all(ba.get(k) == bb.get(k) for k in ("material_sha256", "spec_sha256", "files"))
    ca = Counter(_finding_key(f) for f in ra.get("findings") or [])
    cb = Counter(_finding_key(f) for f in rb.get("findings") or [])
    added, removed = cb - ca, ca - cb
    va, vb = str(ra.get("verdict") or ""), str(rb.get("verdict") or "")
    direction = "same" if rank(va) == rank(vb) else ("stricter" if rank(vb) > rank(va) else "softer")
    sa, sb = ra.get("statuses") or {}, rb.get("statuses") or {}

    def status(group: str):
        return _pair((sa.get(group) or {}).get("status"), (sb.get(group) or {}).get("status"))

    rules_a, rules_b = fa.get("rules") or {}, fb.get("rules") or {}
    rules_changed = {k: {"a": rules_a.get(k), "b": rules_b.get(k)} for k in sorted(set(rules_a) | set(rules_b))
                     if rules_a.get(k) != rules_b.get(k)}
    ea, eb = ba.get("evidence") or {}, bb.get("evidence") or {}

    def ev(*path):
        def dig(e):
            for key in path:
                e = (e or {}).get(key) if isinstance(e, dict) else None
            return e
        return _pair(dig(ea), dig(eb))

    return {
        "a": {"id": a.get("id") or fa.get("id"), "at": a.get("at")},
        "b": {"id": b.get("id") or fb.get("id"), "at": b.get("at")},
        "identical": bool(fa.get("digest")) and fa.get("digest") == fb.get("digest"),
        "same_input": same_input,
        "verdict": {**_pair(va, vb), "direction": direction},
        "fix": status("fix"),
        "verification": status("verification"),
        "findings": {"added": _listed(added), "removed": _listed(removed), "unchanged": sum((ca & cb).values())},
        "rules": rules_changed,
        "evidence": {"snapshot": ev("snapshot", "sha256"), "patch": ev("patch", "diff_sha256"),
                     "sandbox_profile": ev("versions", "sandbox_profile", "sha256"),
                     "attempts": ev("attempts"), "stop_reason": ev("stop_reason")},
        "summary": _summary(va, vb, direction, same_input, added, removed, rules_changed),
    }


def _summary(va, vb, direction, same_input, added, removed, rules_changed) -> str:
    parts = ["the same input" if same_input else "different input (or one run does not record its input)"]
    parts.append(f"verdict {va or '-'} -> {vb or '-'}" + ("" if direction == "same" else f" ({direction})"))
    parts.append(f"{sum(added.values())} finding(s) added, {sum(removed.values())} removed")
    if rules_changed:
        parts.append("rules changed: " + ", ".join(f"{k} {v['a']} -> {v['b']}" for k, v in rules_changed.items()))
    return "; ".join(parts)