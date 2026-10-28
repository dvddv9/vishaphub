"""Contract check: the public names promised by the spec must be importable.

The check runs in a subprocess with a clean environment, so a module that imports
half the world at import time is seen as it really is — by a caller.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from ..models import CheckResult, Finding, Severity, Spec

PROBE = r"""
import importlib, json, sys
sys.path.insert(0, sys.argv[1])
entry, names = sys.argv[2], json.loads(sys.argv[3])
result = {"imported": False, "missing": [], "error": ""}
try:
    module = importlib.import_module(entry)
    result["imported"] = True
    result["missing"] = [n for n in names if not hasattr(module, n)]
except Exception as exc:  # noqa: BLE001 - the point is to report it
    result["error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(result))
"""


def run(root: str, spec: Spec) -> CheckResult:
    if not spec.exports or not spec.entry:
        return CheckResult(
            name="contract",
            ok=True,
            skipped=True,
            skip_reason="spec declares no entry/export names",
        )

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(PROBE)
        probe_path = fh.name
    try:
        proc = subprocess.run(
            [sys.executable, probe_path, root, spec.entry, json.dumps(spec.exports)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=root,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="contract",
            ok=False,
            findings=[
                Finding(
                    check="contract",
                    severity=Severity.CRITICAL,
                    message=f"importing {spec.entry} hung for 60 s",
                    location=spec.entry,
                )
            ],
        )
    finally:
        os.unlink(probe_path)

    findings: list[Finding] = []
    try:
        payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        payload = {"imported": False, "missing": [], "error": (proc.stderr or "probe failed")[:300]}

    if payload["error"]:
        findings.append(
            Finding(
                check="contract",
                severity=Severity.CRITICAL,
                message=f"entry point does not import: {payload['error']}",
                location=spec.entry,
            )
        )
    for name in payload["missing"]:
        findings.append(
            Finding(
                check="contract",
                severity=Severity.HIGH,
                message=f"promised name is missing from {spec.entry}: {name}",
                location=spec.entry,
            )
        )
    return CheckResult(name="contract", ok=not findings, findings=findings)
