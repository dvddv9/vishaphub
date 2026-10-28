# -*- coding: utf-8 -*-
"""Stable identity for findings and a diff between two runs.

A finding keeps its fingerprint when lines above it move, because the fingerprint is built from
file name + rule id + the normalized code on the flagged line, never from the line number. Two
identical lines in one file get ``-1``, ``-2`` suffixes in source order. That is what lets CI say
"2 new, 1 fixed, 14 unchanged" instead of re-reporting the same issue every run, and lets GitHub
code scanning close an alert when the code is fixed (SARIF ``partialFingerprints``).

Deterministic and LLM-free: the same input always gives the same fingerprints.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASELINE_VERSION = "1"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def fingerprint(finding: dict, filename: str = "") -> str:
    key = "|".join([_norm(filename).replace("\\", "/"), str(finding.get("id", "")), _norm(finding.get("snippet", ""))])
    return hashlib.sha256(key.encode("utf-8", errors="replace")).hexdigest()[:16]


def assign_fingerprints(findings: list, filename: str = "") -> list:
    """Set ``finding['fingerprint']`` on every finding (in place) and return the list."""
    seen: dict[str, int] = {}
    for f in sorted(findings, key=lambda x: (int(x.get("line") or 0), str(x.get("id", "")))):
        fp = fingerprint(f, filename)
        n = seen.get(fp, 0)
        seen[fp] = n + 1
        f["fingerprint"] = fp if n == 0 else f"{fp}-{n}"
    return findings


def diff_findings(previous: list | set, current: list) -> dict:
    """Compare two runs. ``previous`` is a list of findings (with fingerprints) or a set of fingerprints."""
    prev_fps = {f["fingerprint"] for f in previous if isinstance(f, dict) and f.get("fingerprint")} \
        if not isinstance(previous, set) else set(previous)
    cur = [f for f in current if f.get("fingerprint")]
    cur_fps = {f["fingerprint"] for f in cur}
    prev_by_fp = {f["fingerprint"]: f for f in previous if isinstance(f, dict) and f.get("fingerprint")} \
        if not isinstance(previous, set) else {}
    return {
        "new": [f for f in cur if f["fingerprint"] not in prev_fps],
        "unchanged": [f for f in cur if f["fingerprint"] in prev_fps],
        "fixed": [prev_by_fp.get(fp, {"fingerprint": fp}) for fp in sorted(prev_fps - cur_fps)],
    }


def save_baseline(findings: list, path: str, filename: str = "") -> int:
    rows = [{"fingerprint": f["fingerprint"], "id": f.get("id"), "title": f.get("title"),
             "severity": f.get("severity"), "line": f.get("line"), "file": f.get("file", filename)}
            for f in findings if f.get("fingerprint")]
    payload = {"version": BASELINE_VERSION, "kind": "vishap-findings",
               "generated_at": datetime.now(timezone.utc).isoformat(), "count": len(rows), "findings": rows}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(rows)


def load_baseline(path: str) -> list:
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = data.get("findings") if isinstance(data, dict) else None
    return [r for r in rows if isinstance(r, dict) and r.get("fingerprint")] if isinstance(rows, list) else []


def render_diff_md(d: dict) -> str:
    out = [f"**Since the baseline:** {len(d['new'])} new, {len(d['fixed'])} fixed, {len(d['unchanged'])} unchanged.", ""]
    for f in d["new"]:
        out.append(f"- NEW {f.get('severity', '')} {f.get('title', f.get('id'))} (line {f.get('line')})")
    for f in d["fixed"]:
        out.append(f"- FIXED {f.get('title') or f.get('id') or f.get('fingerprint')}")
    out.append("")
    return "\n".join(out)
