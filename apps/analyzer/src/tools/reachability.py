# -*- coding: utf-8 -*-
"""P2-7 Reachability: source -> sink path tracing.

Extends detect_exploitability() (boolean) with line-level path.

Architecture:
    patterns.py    -> EXPLOIT_PATTERNS + TAINT_SOURCES + TAINT_SINKS (domain)
    reachability.py -> logic (find_*, trace_taint, enrich_exploitability)

Deterministic: regex + line-based, no LLM.
Fail-open: returns safe defaults on error, does not raise.
Backward compatible: enrich_exploitability() adds new fields,
    keeps all old fields intact, does not mutate input.
"""
from typing import Any

from src.tools.patterns import EXPLOIT_PATTERNS, TAINT_SOURCES, TAINT_SINKS


# --- Language mapping: which entry_point_* patterns apply per language ---

_LANG_ENTRYPOINTS: dict[str, list[str]] = {
    "python": ["entrypoint_web", "entrypoint_func", "entrypoint_main"],
    "go": ["entrypoint_go_main", "entrypoint_go_http"],
    "js": ["entrypoint_js_route"],
    "javascript": ["entrypoint_js_route"],
    # v5.11.5-java-entrypoints
    "java": ["entrypoint_java_main", "entrypoint_java_spring", "entrypoint_java_servlet"],
    # v5.11.6-c-entrypoints
    "c": ["entrypoint_c_main", "entrypoint_c_jni"],
}


def _is_comment_line(line: str) -> bool:
    """Check if a stripped line is a comment (// # * /*)."""
    s = line.strip()
    return s.startswith(("//", "#", "*", "/*"))


# v5.11.5-strip-comments: helper added
def _lines(material: str) -> list[str]:
    """Split material into lines (handle \\r\\n and \\n)."""
    return material.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def find_entry_points(material: str, language: str = "python") -> list[dict]:
    """Find entry points (public API) with line numbers.

    Args:
        material: source code
        language: "python" | "go" | "js" | "javascript"

    Returns:
        [{"line": int, "type": "entry_point", "content": str}, ...]
    """
    if not material:
        return []

    pattern_names = _LANG_ENTRYPOINTS.get(language.lower(), [])
    if not pattern_names:
        return []

    patterns = [EXPLOIT_PATTERNS[n] for n in pattern_names if n in EXPLOIT_PATTERNS]
    result: list[dict] = []

    for i, line in enumerate(_lines(material), 1):
        # v5.11.5-strip-comments
        if _is_comment_line(line):
            continue
        for pat in patterns:
            if pat.search(line):
                result.append({
                    "line": i,
                    "type": "entry_point",
                    "content": line.strip(),
                })
                break  # one match per line is enough

    return result


def find_taint_sources(material: str) -> list[dict]:
    """Find user-input sources with line numbers.

    Returns:
        [{"line": int, "type": "source", "content": str}, ...]
    """
    if not material:
        return []

    patterns = list(TAINT_SOURCES.values())
    result: list[dict] = []

    for i, line in enumerate(_lines(material), 1):
        # v5.11.5-strip-comments
        if _is_comment_line(line):
            continue
        for pat in patterns:
            if pat.search(line):
                result.append({
                    "line": i,
                    "type": "source",
                    "content": line.strip(),
                })
                break

    return result


def find_taint_sinks(material: str) -> list[dict]:
    """Find taint sinks (where data flows out) with line numbers.

    Returns:
        [{"line": int, "type": "sink", "content": str}, ...]
    """
    if not material:
        return []

    patterns = list(TAINT_SINKS.values())
    result: list[dict] = []

    for i, line in enumerate(_lines(material), 1):
        # v5.11.5-strip-comments
        if _is_comment_line(line):
            continue
        for pat in patterns:
            if pat.search(line):
                result.append({
                    "line": i,
                    "type": "sink",
                    "content": line.strip(),
                })
                break

    return result


def trace_taint(material: str, finding: dict | None = None) -> dict:
    """Trace data flow: entry_point -> source -> sink.

    Simplified deterministic taint analysis:
    - source before sink on a line => reachable
    - finding.line (if given) bounds the search to <= finding_line

    Args:
        material: source code
        finding: optional {"line": int, "message": str}

    Returns:
        {
            "reachable": bool,
            "path": [{"line": int, "type": str, "content": str}, ...],
            "source_count": int,
            "sources": [{"line": int, "content": str}, ...],
            "entry_points": [{"line": int, "content": str}, ...],
            "sinks": [{"line": int, "content": str}, ...],
        }
    """
    try:
        sources = find_taint_sources(material)
        sinks = find_taint_sinks(material)
        # entry_points: detect language by trying python first (most common),
        # then go, then js — first non-empty wins
        entries: list[dict] = []
        # v5.11.5-java-entrypoints: added "java"
        # v5.11.6: added "c"
        for lang in ("python", "go", "js", "java", "c"):
            entries = find_entry_points(material, language=lang)
            if entries:
                break
    except Exception:
        # fail-open
        return {
            "reachable": False,
            "path": [],
            "source_count": 0,
            "sources": [],
            "entry_points": [],
            "sinks": [],
        }

    if not sources or not sinks:
        return {
            "reachable": False,
            "path": [],
            "source_count": len(sources),
            "sources": [{"line": s["line"], "content": s["content"]} for s in sources],
            "entry_points": [{"line": e["line"], "content": e["content"]} for e in entries],
            "sinks": [{"line": s["line"], "content": s["content"]} for s in sinks],
        }

    # Reachable if at least one source comes before at least one sink
    first_sink_line = min(s["line"] for s in sinks)
    relevant_sources = [s for s in sources if s["line"] <= first_sink_line]

    if not relevant_sources:
        return {
            "reachable": False,
            "path": [],
            "source_count": len(sources),
            "sources": [{"line": s["line"], "content": s["content"]} for s in sources],
            "entry_points": [{"line": e["line"], "content": e["content"]} for e in entries],
            "sinks": [{"line": s["line"], "content": s["content"]} for s in sinks],
        }

    # Build path: entry_point (earliest) -> source(s) -> sink(earliest)
    path: list[dict] = []
    if entries:
        ep = min(entries, key=lambda x: x["line"])
        path.append({"line": ep["line"], "type": "entry_point", "content": ep["content"]})
    for s in relevant_sources:
        path.append({"line": s["line"], "type": "source", "content": s["content"]})
    first_sink = min(sinks, key=lambda x: x["line"])
    path.append({"line": first_sink["line"], "type": "sink", "content": first_sink["content"]})

    return {
        "reachable": True,
        "path": path,
        "source_count": len(sources),
        "sources": [{"line": s["line"], "content": s["content"]} for s in sources],
        "entry_points": [{"line": e["line"], "content": e["content"]} for e in entries],
        "sinks": [{"line": s["line"], "content": s["content"]} for s in sinks],
    }


def enrich_exploitability(
    material: str,
    exploitability: dict,
    language: str = "python",
) -> dict:
    """Enrich exploitability with path/source_count (backward compatible).

    Does NOT mutate input. Returns a new dict with:
    - all old fields preserved
    - new: path (list), source_count (int), sources (list),
           entry_points_lines (list), sinks (list)
    """
    if not isinstance(exploitability, dict):
        return {}

    # start from a copy (do not mutate caller's dict)
    result: dict[str, Any] = dict(exploitability)

    try:
        traced = trace_taint(material)
    except Exception:
        traced = {
            "reachable": result.get("reachable", False),
            "path": [],
            "source_count": 0,
            "sources": [],
            "entry_points": [],
            "sinks": [],
        }

    result["path"] = traced["path"]
    result["source_count"] = traced["source_count"]
    result["sources"] = traced["sources"]
    result["entry_points_lines"] = traced["entry_points"]
    result["sinks"] = traced["sinks"]

    return result
