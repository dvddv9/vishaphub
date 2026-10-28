# -*- coding: utf-8 -*-
"""Report noise filter: remove lines that carry no information.

The LLM report template has slots (ECON, SLO IMPACT, CLOUD COST, ...). When there is no data the
model fills them with "NOT SET" / "n/a", which a reader has to wade through. A line under one of
those labels is dropped when nothing is left of it once placeholders are removed (no number and no
';'-separated part without a placeholder). The
label itself is kept (one short line lists them) so the section structure and the completeness
check, which looks for the bracketed block headers, are untouched.

Deterministic, no LLM. Turn it off with VISHAP_TRIM_REPORT=0.
"""
from __future__ import annotations

import os
import re

_LABELS = ("ECONOMICS", "ECON", "SLO IMPACT", "CLOUD COST", "PRODUCTION IMPACT", "ON-CALL", "INFRASTRUCTURE")
_LINE = re.compile(r"^(\s*)(" + "|".join(re.escape(x) for x in _LABELS) + r"):\s*(.*)$")
_PLACEHOLDER = re.compile(
    r"NOT[ _]SET|\bN/?A\b|не вычислим\w*|не оценён\w*|не оценен\w*|не задан\w*|\(?VERIFY[^;.)]*\)?|при условии[^;.]*|"
    r"requires? confirmation|требует подтверждения[^;.]*", re.I)
_MARK = "\x00NODATA\x00"


def trim_enabled() -> bool:
    return os.environ.get("VISHAP_TRIM_REPORT", "1").strip().lower() not in ("0", "false", "no", "off")


def has_substance(rest: str) -> bool:
    """True if the line says something: a number outside the placeholders, or a ';'-separated
    part that has no placeholder in it (e.g. 'rollback: git revert', 'runbook does not exist')."""
    if re.search(r"\d", _PLACEHOLDER.sub("", rest)):
        return True
    for part in rest.split(";"):
        if not _PLACEHOLDER.search(part) and len(re.findall(r"[^\W\d_]", part)) >= 4:
            return True
    return False


def trim_noise(md: str) -> str:
    """Drop placeholder-only lines under the template labels; keep one 'no data' line instead."""
    if not md:
        return md
    dropped: list[str] = []
    out: list[str] = []
    for line in md.split("\n"):
        m = _LINE.match(line)
        if m and not has_substance(m.group(3)):
            if m.group(2) not in dropped:
                dropped.append(m.group(2))
            out.append(_MARK)
            continue
        out.append(line)
    if not dropped:
        return md
    summary = "No data for: " + ", ".join(dropped) + "."
    first = True
    final = []
    for line in out:
        if line == _MARK:
            if first:
                final.append(summary)
                first = False
            continue
        final.append(line)
    return "\n".join(final)
