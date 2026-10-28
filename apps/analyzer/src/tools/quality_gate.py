# -*- coding: utf-8 -*-
"""Quality Gates for Vishap (P1-5).

Reads .vishap.yml (or path via --config), evaluates findings against
thresholds, returns pass/fail + reasons. CI uses exit code to break build.

Config example (.vishap.yml):
    quality_gate:
      fail_on: [critical]
      warn_on: [high, medium]
      ignore: [low, info]
      ignore_rules: [CWE-79]
      ignore_paths: [tests/, examples/]
      max_critical: 0
      max_high: 10
      fail_on_reachable: true
"""
from __future__ import annotations

from pathlib import Path

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


DEFAULT_CONFIG = {
    "fail_on": ["critical"],
    "warn_on": ["high", "medium"],
    "ignore": ["low", "info"],
    "ignore_rules": [],
    "ignore_paths": [],
    "max_critical": 0,
    "max_high": 10,
    "fail_on_reachable": False,
}


def load_quality_gate(path: str = ".vishap.yml") -> dict:
    """Load .vishap.yml quality_gate section. Falls back to DEFAULT_CONFIG."""
    p = Path(path)
    if not p.exists() or not _HAS_YAML:
        return dict(DEFAULT_CONFIG)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        return dict(DEFAULT_CONFIG)
    if not isinstance(data, dict):
        return dict(DEFAULT_CONFIG)
    cfg = data.get("quality_gate", {})
    if not isinstance(cfg, dict):
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


_PRIORITY_MAP = {
    "критично": "critical",
    "critical": "critical",
    "high": "high",
    "важно": "high",
    "medium": "medium",
    "moderate": "medium",
    "опционально": "medium",
    "low": "low",
    "info": "info",
}


def normalize_priority(value: str) -> str:
    """Normalize priority (RU/EN) to canonical severity."""
    if not value:
        return "low"
    s = str(value).strip().lower()
    return _PRIORITY_MAP.get(s, "low")


def _normalize_path(p: str) -> str:
    if not p:
        return ""
    s = str(p).strip().replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s


def evaluate_gate(findings: list, config: dict,
                  reachable: bool = False,
                  verbose: bool = False) -> dict:
    """Evaluate findings against quality gate config.

    Args:
        findings: list of risk_node dicts (id, name, priority, note) OR
                  dicts with 'severity'/'cwe'/'file' fields.
        config: dict from load_quality_gate (or partial).
        reachable: audit-level exploitability.reachable flag.

    Returns:
        {
            "passed": bool,
            "critical": int, "high": int, "medium": int, "low": int,
            "total": int,
            "reasons": list[str],
            "ignored": int,
        }
    """
    if not isinstance(findings, list):
        findings = []
    if not isinstance(config, dict):
        config = dict(DEFAULT_CONFIG)

    ignore_sev = set(str(x).lower() for x in config.get("ignore", []))
    ignore_rules = set(str(x) for x in config.get("ignore_rules", []))
    ignore_paths = [_normalize_path(p) for p in config.get("ignore_paths", [])]

    relevant = []
    ignored = 0

    for f in findings:
        if not isinstance(f, dict):
            continue
        sev = normalize_priority(f.get("priority") or f.get("severity"))
        cwe = str(f.get("cwe", ""))
        filep = _normalize_path(f.get("file", ""))

        if sev in ignore_sev:
            ignored += 1
            continue
        if cwe and cwe in ignore_rules:
            ignored += 1
            continue
        if filep and any(filep.startswith(ip) for ip in ignore_paths if ip):
            ignored += 1
            continue

        relevant.append({"sev": sev, "f": f})

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for r in relevant:
        counts[r["sev"]] = counts.get(r["sev"], 0) + 1

    failed = False
    reasons = []

    max_critical = int(config.get("max_critical", 0))
    max_high = int(config.get("max_high", 10))

    if counts["critical"] > max_critical:
        failed = True
        reasons.append(f"critical: {counts['critical']} > max {max_critical}")

    if counts["high"] > max_high:
        failed = True
        reasons.append(f"high: {counts['high']} > max {max_high}")

    if config.get("fail_on_reachable") and reachable:
        failed = True
        reasons.append("reachable: exploitability.reachable=true")

    if verbose:
        print(f"[Gate] findings={len(findings)} relevant={len(relevant)} ignored={ignored}")
        print(f"[Gate] critical={counts['critical']} high={counts['high']} "
              f"medium={counts['medium']} low={counts['low']}")

    return {
        "passed": not failed,
        "critical": counts["critical"],
        "high": counts["high"],
        "medium": counts["medium"],
        "low": counts["low"],
        "total": len(relevant),
        "ignored": ignored,
        "reasons": reasons,
    }
