"""A person's note on a finding: accepted, and why. It sits beside the finding and never changes the verdict.

The rules decide the verdict and the model can only raise it; a human saying "this one is fine here" is a third
thing, and it is kept as what it is: who, when and the reason, shown next to the finding in the report. The finding
is still listed, the verdict is still the one the checks gave, and the SARIF of the run still has it.

The marks live inside the run's own result (`result["accepted"]`, keyed by a short digest of the finding), so
there is no new table: a run that expires takes its marks with it, and a re-run of the same material keeps them.
"""
from __future__ import annotations

import fnmatch
import hashlib
import re

MAX_MARKS = 100
MAX_REASON = 300
MAX_RULES = 50
_FIELDS = {"cwe", "rule", "file", "reason"}
_CWE = re.compile(r"(?i)^\s*(?:cwe[-_ ]?)?0*(\d{1,5})\s*$")


def _cwe_number(text: str) -> int | None:
    match = _CWE.match(text or "")
    return int(match.group(1)) if match and int(match.group(1)) > 0 else None


def parse_rules(raw: object) -> list[dict]:
    """Standing rules a client sends with a run: "accept findings like this, for this reason".

    Each names at least one of `cwe`, `rule`, `file` (a glob) and gives a reason. A rule that would match every
    finding is refused: that is not a rule, it is a way to silence the report. Raises ValueError in words a
    person can read.
    """
    if not isinstance(raw, list):
        raise ValueError("expected a list of rules")  # noqa: TRY004 - a refusal the caller prints, not a bug
    if len(raw) > MAX_RULES:
        raise ValueError(f"at most {MAX_RULES} rules")
    out = []
    for n, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"rule {n}: expected an object")  # noqa: TRY004 - a refusal the caller prints, not a bug
        unknown = sorted(set(item) - _FIELDS)
        if unknown:
            raise ValueError(f"rule {n}: unknown field {unknown[0]!r}")
        reason = item.get("reason")
        reason = reason.strip() if isinstance(reason, str) else ""
        if not reason:
            raise ValueError(f"rule {n}: a reason is required")
        if len(reason) > MAX_REASON:
            raise ValueError(f"rule {n}: the reason is longer than {MAX_REASON} characters")
        rule = {"reason": reason}
        for name in ("cwe", "rule", "file"):
            value = item.get(name)
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip() or len(value) > 120:
                raise ValueError(f"rule {n}: {name!r} must be a short text")
            rule[name] = value.strip()
        if len(rule) == 1:
            raise ValueError(f"rule {n}: name at least one of cwe, rule, file; a rule that matches everything is refused")
        if "cwe" in rule and _cwe_number(rule["cwe"]) is None:
            raise ValueError(f"rule {n}: {rule['cwe']!r} is not a CWE id")
        out.append(rule)
    return out


def _matches(finding: dict, rule: dict) -> bool:
    if "cwe" in rule:
        have = _cwe_number(str(finding.get("cwe") or "")) or _cwe_number(str(finding.get("rule") or ""))
        if have != _cwe_number(rule["cwe"]):
            return False
    if "rule" in rule and str(finding.get("rule") or "") != rule["rule"]:
        return False
    if "file" in rule:
        name = str(finding.get("file") or "").replace("\\", "/").lower()
        pattern = rule["file"].lower()
        if not (fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(name.rsplit("/", 1)[-1], pattern)):
            return False
    return True


def standing(findings: list, rules: list[dict], at: str) -> dict:
    """The notes the rules put on these findings: `by` is `rule:<n>`, the first rule that matches wins.

    A finding about the model's own patch is not matched: a rule is about the material the person sent.
    """
    marks: dict = {}
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("in_patch"):
            continue
        for n, rule in enumerate(rules, 1):
            if _matches(finding, rule):
                key = key_of(finding)
                if key not in marks and len(marks) < MAX_MARKS:
                    marks[key] = {"reason": rule["reason"], "by": f"rule:{n}", "at": str(at)}
                break
    return marks


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