# -*- coding: utf-8 -*-
"""What SAFE means, and the only place that decides it.

A SAFE verdict is built on rules that find some defects and miss others. So "the rules found nothing" is not the
same as "there is nothing", and this module does not let one stand for the other. SAFE is issued only when all three
hold:

  1. the rules found nothing in the text;
  2. the scan could see all of the text (`coverage.complete`: the language was recognised and has rules of its own,
     no line was cut, no part of the analysis quietly failed);
  3. the rules for that language have been MEASURED against an independently labelled blind set and passed the gates
     written down before the measurement (tests/bench/blind_public/CRITERION.md), recorded in quality.json.

Anything else is REQUIRES_REVIEW, with the reason. A language that is not in quality.json is unmeasured, and
unmeasured is unknown coverage. A missing or unreadable quality.json fails closed: nothing is SAFE.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

QUALITY_FILE = Path(__file__).with_name("quality.json")

MEANING = (
    "SAFE: the built-in rules, measured against an independent blind set for this language, found nothing in the "
    "text, and the scan could read all of it. It is not a claim that the code has no vulnerabilities: the rules do "
    "not look for every class of defect (authorization, business logic, dependencies, runtime configuration)."
)


def wilson_upper(failures: int, n: int, z: float = 1.96) -> float:
    """Upper end of the 95% Wilson interval for failures out of n. 1.0 when there is nothing to measure."""
    if n <= 0:
        return 1.0
    p = failures / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return min(1.0, (centre + margin) / denom)


def load_quality(path: Path | None = None) -> dict:
    """quality.json, or an empty verdict-nothing table when it is absent or unreadable (fail closed)."""
    try:
        data = json.loads((path or QUALITY_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("languages"), dict) else {"languages": {}}
    except (OSError, ValueError):
        return {"languages": {}}


def rules_found_nothing(scan: dict) -> bool:
    """The raw fact the benchmark measures: no finding, and the scan was complete. Not yet a verdict."""
    coverage = scan.get("coverage") or {}
    return not (scan.get("findings") or []) and bool(coverage.get("complete"))


def evaluate_gates(stats: dict, criterion: dict) -> dict:
    """Apply the registered gates to one language's counts. stats: dangerous, safe, false_safe, critical_false_safe."""
    need = criterion["measured_language"]
    limit = criterion["gates_per_language"]["G2_false_safe_upper_bound"]["max_upper_95_wilson"]
    measured = stats["dangerous"] >= need["min_dangerous"] and stats["safe"] >= need["min_safe"]
    upper = wilson_upper(stats["false_safe"], stats["dangerous"])
    g1 = stats["critical_false_safe"] == 0
    g2 = upper <= limit
    if not measured:
        why = (f"unmeasured: {stats['dangerous']} dangerous and {stats['safe']} safe examples, "
               f"{need['min_dangerous']} and {need['min_safe']} are needed")
    elif not g1:
        why = f"G1 failed: {stats['critical_false_safe']} critical example(s) got SAFE"
    elif not g2:
        why = (f"G2 failed: {stats['false_safe']} of {stats['dangerous']} dangerous examples got SAFE "
               f"(95% upper bound {upper:.1%}, limit {limit:.0%})")
    else:
        why = "passed G1 and G2"
    return {"measured": measured, "g1": g1, "g2": g2, "false_safe_upper_95": round(upper, 4),
            "safe_allowed": measured and g1 and g2, "why": why}


def decide(scan: dict, quality: dict | None = None) -> dict:
    """The verdict for one scan: {verdict, reason, critical, meaning}. SAFE or REQUIRES_REVIEW, never anything softer."""
    quality = quality if quality is not None else load_quality()
    findings = scan.get("findings") or []
    coverage = scan.get("coverage") or {}
    lang = coverage.get("language") or scan.get("language") or ""
    critical = any(str(f.get("severity", "")).lower() == "critical" for f in findings)

    def review(reason: str) -> dict:
        return {"verdict": "REQUIRES_REVIEW", "reason": reason, "critical": critical, "meaning": MEANING}

    if findings:
        worst = min((str(f.get("severity", "low")).lower() for f in findings),
                    key=lambda s: ("critical", "high", "medium", "low").index(s) if s in ("critical", "high", "medium", "low") else 9)
        return review(f"{len(findings)} finding(s); worst severity {worst}" + ("; at least one is critical" if critical else ""))
    if not coverage:
        return review("unknown coverage: the scan did not say what it could see")
    if not coverage.get("complete"):
        return review("unknown coverage: " + "; ".join(coverage.get("gaps") or ["incomplete scan"]))
    entry = (quality.get("languages") or {}).get(lang)
    if not entry or not entry.get("safe_allowed"):
        why = (entry or {}).get("why") or f"{lang or 'this language'} has no measurement"
        return review(f"unknown coverage: the rules for {lang or 'this language'} have no passing measurement ({why})")
    return {"verdict": "SAFE", "critical": False, "meaning": MEANING,
            "reason": (f"the rules found nothing in the {lang} text; measured on {entry['dangerous']} dangerous and "
                       f"{entry['safe']} safe independent examples, false-SAFE upper bound {entry['false_safe_upper_95']:.0%}")}