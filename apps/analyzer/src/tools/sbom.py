# -*- coding: utf-8 -*-
"""SBOM generation via cyclonedx-bom (CycloneDX standard).

Wraps `cyclonedx-py` CLI to produce a Software Bill of Materials in
CycloneDX JSON format. Tolerant to missing tool / errors -- never raises.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

CYCLONEDX_CMD = "cyclonedx-py"
DEFAULT_SOURCE = "environment"


def _run_cyclonedx(source: str, timeout: int = 60) -> str:
    """Run cyclonedx-py <source> --output-format json. Return stdout or ''."""
    cmd = [CYCLONEDX_CMD, source, "--output-format", "json"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            errors="replace",
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def generate_sbom(output_path: str = None, source: str = DEFAULT_SOURCE) -> dict:
    """Generate CycloneDX SBOM. Returns dict, empty on error."""
    raw = _run_cyclonedx(source)
    if not raw:
        return {}
    try:
        sbom = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(sbom, dict):
        return {}
    if output_path:
        try:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(sbom, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return sbom


def parse_sbom(sbom: dict) -> dict:
    """Extract summary: count, spec_version, bom_format, serial_number."""
    if not isinstance(sbom, dict):
        return {"count": 0, "spec_version": "", "bom_format": "", "serial_number": ""}
    components = sbom.get("components", [])
    if not isinstance(components, list):
        components = []
    return {
        "count": len(components),
        "spec_version": str(sbom.get("specVersion", "")),
        "bom_format": str(sbom.get("bomFormat", "")),
        "serial_number": str(sbom.get("serialNumber", "")),
    }


def is_cyclonedx_available() -> bool:
    """True if cyclonedx-py CLI is available."""
    try:
        result = subprocess.run(
            [CYCLONEDX_CMD, "--version"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0
