# -*- coding: utf-8 -*-
"""Baseline management for Vishap. Fingerprint-based, stable across re-runs."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

BASELINE_VERSION = "1.0"
TOOL_VERSION = "5.9.0"


def _normalize(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def compute_fingerprint(risk_node: dict, filename: str = "") -> str:
    parts = [
        _normalize(filename),
        _normalize(risk_node.get("name", "")),
        _normalize(risk_node.get("priority", "")),
        _normalize(risk_node.get("note", ""))[:100],
    ]
    key = "|".join(parts)
    return hashlib.sha256(key.encode("utf-8", errors="replace")).hexdigest()[:16]


def save_baseline(risk_nodes: Iterable[dict], path: str, filename: str = "") -> int:
    fps = sorted({compute_fingerprint(rn, filename) for rn in risk_nodes if rn})
    payload = {
        "version": BASELINE_VERSION,
        "tool_version": TOOL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": filename,
        "count": len(fps),
        "fingerprints": fps,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(fps)


def load_baseline(path: str) -> set:
    p = Path(path)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return set()
    if not isinstance(data, dict):
        return set()
    fps = data.get("fingerprints", [])
    if not isinstance(fps, list):
        return set()
    return {str(fp) for fp in fps if fp}


def filter_new(risk_nodes: Iterable[dict], baseline: set, filename: str = ""):
    new, known = [], []
    for rn in risk_nodes:
        fp = compute_fingerprint(rn, filename)
        rn["fingerprint"] = fp
        if fp in baseline:
            known.append(rn)
        else:
            new.append(rn)
    return new, known


def apply_baseline(result: dict, baseline_path: str = None,
                   save_baseline_path: str = None,
                   filename: str = "", verbose: bool = False) -> dict:
    stage2 = result.get("stage2") or {}
    risk_nodes = stage2.get("risk_nodes", []) or []
    for rn in risk_nodes:
        rn.setdefault("fingerprint", compute_fingerprint(rn, filename))
    stats = {
        "baseline_used": False,
        "baseline_saved": False,
        "baseline_path": baseline_path or "",
        "baseline_save_path": save_baseline_path or "",
        "baseline_known": 0,
        "baseline_new": len(risk_nodes),
        "baseline_total": len(risk_nodes),
    }
    if save_baseline_path:
        try:
            count = save_baseline(risk_nodes, save_baseline_path, filename)
            stats["baseline_saved"] = True
            stats["baseline_saved_count"] = count
            if verbose:
                print("[Baseline] Saved " + str(count) + " -> " + save_baseline_path)
        except OSError as e:
            stats["baseline_save_error"] = str(e)
            if verbose:
                print("[Baseline] Save error: " + str(e))
    if baseline_path:
        baseline = load_baseline(baseline_path)
        new, known = filter_new(risk_nodes, baseline, filename)
        stats["baseline_used"] = True
        stats["baseline_known"] = len(known)
        stats["baseline_new"] = len(new)
        result["new_findings"] = new
        result["known_findings"] = known
        if verbose:
            print("[Baseline] New: " + str(len(new)) + " / Known: " + str(len(known)))
    result["baseline_stats"] = stats
    return stats
