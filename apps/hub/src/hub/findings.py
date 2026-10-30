"""Findings from two readers of the same text, told apart and joined where they agree.

A review has two readers: the model, which reads for meaning, and the rules, which match patterns. They find
different things, and the same thing in different words (`CWE-89` and `sqli-fstring`). Listing both as separate
findings made one injection look like two and hid the one fact worth knowing - that two independent readers saw it.

This module pairs a model finding with a rules finding when they name the same class of defect near the same line,
and says for every finding who saw it: `seen_by` is `["rules"]`, `["model"]` or both. It never drops a finding: an
unpaired one stays, marked with its single reader. The rules' findings about the model's own patch are a different
question (is the proposed fix itself clean?) and are left alone.
"""
from __future__ import annotations

import re

SEVERITY = {"critical": 4, "high": 3, "medium": 2, "low": 1}

#: Missing or insufficient authentication / authorization: the model says CWE-306, the rules CWE-862, and they mean
#: the same open door.
AUTH_FAMILY = {"284", "285", "306", "862", "863"}

#: A model's line numbers are approximate and a decorator is not the function under it: pair within this many lines.
WINDOW = 3


def _family(finding: dict) -> str | None:
    for key in ("cwe", "rule"):
        match = re.fullmatch(r"(?i)cwe[-_ ]?(\d+)", str(finding.get(key) or "").strip())
        if match:
            number = match.group(1)
            return "auth" if number in AUTH_FAMILY else number
    return None


def _line(finding: dict) -> int:
    try:
        return int(finding.get("line") or 0)
    except (TypeError, ValueError):
        return 0


def _stricter(a: object, b: object) -> str:
    a, b = str(a or ""), str(b or "")
    return a if SEVERITY.get(a.lower(), 0) >= SEVERITY.get(b.lower(), 0) else b


def merge(model: list, rules: list) -> tuple[list[dict], dict]:
    """Return the findings, one list, each with `seen_by`, and how the two readers overlapped."""
    model = [dict(m) for m in model if isinstance(m, dict)]
    rules = [dict(r) for r in rules if isinstance(r, dict)]
    taken: set[int] = set()
    out: list[dict] = []
    both = rules_only = in_patch = 0
    paired: dict[str, str] = {}

    for rule_finding in rules:
        if str(rule_finding.get("source") or "") != "material":
            out.append({**rule_finding, "seen_by": ["rules"], "in_patch": True})
            in_patch += 1
            continue
        family = _family(rule_finding)
        best: tuple[int, int] | None = None
        if family:
            for i, candidate in enumerate(model):
                if i in taken or _family(candidate) != family:
                    continue
                a, b = _line(rule_finding), _line(candidate)
                if a and b and abs(a - b) > WINDOW:
                    continue
                gap = abs(a - b) if a and b else WINDOW + 1
                if best is None or gap < best[0]:
                    best = (gap, i)
        if best is None:
            out.append({**rule_finding, "seen_by": ["rules"]})
            rules_only += 1
            continue
        taken.add(best[1])
        seen = model[best[1]]
        both += 1
        paired.setdefault(family, f"{seen.get('rule') or 'model'} @ {seen.get('line') or '?'}")
        out.append({
            **rule_finding,
            "severity": _stricter(rule_finding.get("severity"), seen.get("severity")),
            "message": seen.get("message") or rule_finding.get("message") or "",   # the model explains, the rules name
            "rules_message": rule_finding.get("message") or "",
            "line": rule_finding.get("line") or seen.get("line") or 0,
            "model_rule": seen.get("rule") or "",
            "seen_by": ["rules", "model"],
        })

    model_only = 0
    for i, finding in enumerate(model):
        if i not in taken:
            out.append({**finding, "source": "model", "seen_by": ["model"]})
            model_only += 1

    # The model often writes one finding for the whole application ("neither endpoint has authentication"). The rules
    # then report the other route separately. It stays - it is a real second place - but says what may already cover it.
    for f in out:
        if f["seen_by"] == ["rules"] and not f.get("in_patch") and _family(f) == "auth" and "auth" in paired:
            f["possibly_covered_by"] = paired["auth"]

    out.sort(key=lambda f: (-SEVERITY.get(str(f.get("severity") or "").lower(), 0), -len(f["seen_by"]), _line(f)))
    return out, {"both": both, "model_only": model_only, "rules_only": rules_only, "in_patch": in_patch}