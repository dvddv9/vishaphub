# -*- coding: utf-8 -*-
"""P2-8 Compliance Mapping: CWE -> concrete standard controls.

Extends compliance_flags (list[str]) with compliance_controls (dict).

Architecture:
    patterns.py     -> COMPLIANCE_MAP (data)
    compliance.py   -> map_compliance(), enrich_compliance() (logic)

Deterministic: dict-lookup only, no LLM.
Fail-open: returns safe defaults on error.
Backward compatible: adds new fields, keeps compliance_flags intact.
"""
from src.tools.patterns import COMPLIANCE_MAP


def map_compliance(cwe_ids: list[str], standards: list[str] | None = None) -> dict:
    """Map CWE IDs to concrete compliance controls.

    Args:
        cwe_ids: e.g. ["CWE-89", "CWE-79"]
        standards: filter, e.g. ["PCI-DSS", "GDPR"]. None = all.

    Returns:
        {"PCI-DSS": ["Req 6.5.1", "Req 6.5.7"],
         "GDPR":    ["Art. 32"],
         ...}
        Empty dict if no matches. Controls per standard are sorted.
    """
    if not cwe_ids:
        return {}

    try:
        if isinstance(standards, str):
            standards = [standards]
        target_standards = list(standards) if standards else list(COMPLIANCE_MAP.keys())
    except Exception:
        return {}

    result: dict[str, list[str]] = {}

    for std in target_standards:
        std_map = COMPLIANCE_MAP.get(std)
        if not std_map:
            continue
        controls: set[str] = set()
        for cwe in cwe_ids:
            for ctrl in std_map.get(cwe, []):
                controls.add(ctrl)
        if controls:
            result[std] = sorted(controls)

    return result


def enrich_compliance(
    cwe_ids: list[str],
    compliance_flags: list[str],
    standards: list[str] | None = None,
) -> dict:
    """Enrich compliance data with concrete controls (backward compatible).

    Does NOT mutate inputs.

    Args:
        cwe_ids: e.g. ["CWE-89"]
        compliance_flags: existing list, e.g. ["PCI-DSS", "GDPR"]
        standards: optional filter for map_compliance()

    Returns:
        {
            "compliance_flags": [...],          # unchanged
            "compliance_controls": {...},       # NEW: CWE -> controls
            "compliance_standards": [...],      # NEW: sorted std keys
        }
    """
    try:
        flags_copy = list(compliance_flags) if compliance_flags else []
    except Exception:
        flags_copy = []

    try:
        cwes_copy = list(cwe_ids) if cwe_ids else []
    except Exception:
        cwes_copy = []

    try:
        controls = map_compliance(cwes_copy, standards=standards)
    except Exception:
        controls = {}

    return {
        "compliance_flags": flags_copy,
        "compliance_controls": controls,
        "compliance_standards": sorted(controls.keys()),
    }
