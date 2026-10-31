"""Findings from a scanner the hub did not run, read as a third reader and never trusted over the rules.

A client may send the SARIF of Semgrep, OpenGrep, CodeQL or any other scanner together with the files. The hub
does not take those findings as its own and does not throw them away:

- a finding that names the same class of defect near the same line as one the hub already has is that finding seen
  by one more reader (`seen_by` gains `external`);
- a finding nothing else saw stays in the list, marked `["external"]`, and raises the verdict to REQUIRES_REVIEW.
  It can only raise it. An external scanner that found nothing says nothing, so it never lowers a verdict.

Nothing is dropped: whatever cannot be read is counted and the count is shown.
"""
from __future__ import annotations

import re

from . import findings as findings_mod

#: More than this many results from one SARIF document are counted but not read.
MAX_EXTERNAL = 300
MAX_TEXT = 300

_LEVEL = {"error": "high", "warning": "medium", "note": "low", "none": "low"}
_CWE = re.compile(r"(?i)cwe[-_/ :]*0*(\d{1,5})")


def _d(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value: object, limit: int = MAX_TEXT) -> str:
    return str(value or "").strip()[:limit]


def _severity(result: dict, rule: dict) -> str:
    for props in (_d(result.get("properties")), _d(rule.get("properties"))):
        try:
            score = float(props.get("security-severity"))
        except (TypeError, ValueError):
            continue
        if score >= 9:
            return "critical"
        if score >= 7:
            return "high"
        if score >= 4:
            return "medium"
        return "low"
    level = str(result.get("level") or _d(rule.get("defaultConfiguration")).get("level") or "warning").lower()
    return _LEVEL.get(level, "medium")


def _cwe(result: dict, rule: dict) -> str:
    texts: list[str] = []
    for obj in (result, rule):
        props = _d(obj.get("properties"))
        tags = props.get("tags")
        if isinstance(tags, list):
            texts.extend(str(tag) for tag in tags)
        texts.append(str(props.get("cwe") or ""))
    texts.append(str(result.get("ruleId") or ""))
    for text in texts:
        match = _CWE.search(text)
        if match and int(match.group(1)) > 0:
            return f"CWE-{int(match.group(1))}"
    return ""


def _location(result: dict) -> tuple[str, int]:
    locations = result.get("locations")
    first = _d(locations[0]) if isinstance(locations, list) and locations else {}
    physical = _d(first.get("physicalLocation"))
    uri = _text(_d(physical.get("artifactLocation")).get("uri"), 200)
    uri = uri.removeprefix("file://")
    try:
        line = int(_d(physical.get("region")).get("startLine") or 0)
    except (TypeError, ValueError):
        line = 0
    return uri, max(line, 0)


def parse_sarif(doc: object) -> tuple[list[dict], list[str]]:
    """The findings of a SARIF document, and a note for whatever was skipped.

    Raises ValueError for something that is not SARIF at all: a refusal the caller can print.
    """
    if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list):
        raise ValueError("not a SARIF document: there is no 'runs' list")  # noqa: TRY004 - a refusal the caller prints, not a bug
    out: list[dict] = []
    skipped = 0
    for run in doc["runs"]:
        run = _d(run)
        driver = _d(_d(run.get("tool")).get("driver"))
        tool = _text(driver.get("name") or "external scanner", 60)
        rules = {str(r["id"]): r for r in (driver.get("rules") or []) if isinstance(r, dict) and r.get("id")}
        for result in run.get("results") or []:
            if not isinstance(result, dict) or len(out) >= MAX_EXTERNAL:
                skipped += 1
                continue
            rule_id = _text(result.get("ruleId"), 120)
            rule = _d(rules.get(rule_id))
            uri, line = _location(result)
            message = (_text(_d(result.get("message")).get("text"))
                       or _text(_d(rule.get("shortDescription")).get("text")) or rule_id)
            out.append({
                "rule": rule_id or "external",
                "cwe": _cwe(result, rule),
                "severity": _severity(result, rule),
                "message": message,
                "line": line,
                "file": uri,
                "source": "external",
                "tool": tool,
            })
    notes = []
    if skipped:
        notes.append(f"{skipped} external result(s) were not read (more than {MAX_EXTERNAL}, or malformed)")
    return out, notes


def _base(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").split("/")[-1].lower()


def attach(found: list, external: list) -> tuple[list[dict], dict]:
    """Join the external findings to the hub's own. Returns the list, and how many were paired or stand alone.

    A pair needs the same class of defect (`findings._family`), a line known on both sides within
    `findings.WINDOW`, and the same file name when both sides name one. Anything else stands alone.
    """
    out = [dict(f) for f in found if isinstance(f, dict)]
    paired = alone = 0
    read = [e for e in external if isinstance(e, dict)]
    for ext in read:
        family, line = findings_mod._family(ext), findings_mod._line(ext)
        best: tuple[int, int] | None = None
        if family and line:
            for i, mine in enumerate(out):
                if mine.get("in_patch") or findings_mod._family(mine) != family:
                    continue
                other = findings_mod._line(mine)
                if not other or abs(other - line) > findings_mod.WINDOW:
                    continue
                a, b = str(ext.get("file") or ""), str(mine.get("file") or "")
                if a and b and _base(a) != _base(b):
                    continue
                if best is None or abs(other - line) < best[0]:
                    best = (abs(other - line), i)
        if best is None:
            out.append({**ext, "seen_by": ["external"]})
            alone += 1
            continue
        mine = out[best[1]]
        seen = list(mine.get("seen_by") or [])
        if "external" not in seen:
            seen.append("external")
        out[best[1]] = {**mine, "seen_by": seen, "external_tool": ext.get("tool", ""),
                        "external_rule": ext.get("rule", "")}
        paired += 1
    tools = sorted({str(e.get("tool") or "") for e in read} - {""})
    return out, {"received": len(read), "paired": paired, "external_only": alone, "tools": tools}