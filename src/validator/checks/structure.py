"""Structure check: does the deliverable contain what the spec listed?"""
from __future__ import annotations

import os

from ..models import CheckResult, Finding, Severity, Spec


def run(root: str, spec: Spec) -> CheckResult:
    findings: list[Finding] = []
    for rel in spec.files:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            findings.append(
                Finding(
                    check="structure",
                    severity=Severity.CRITICAL,
                    message=f"expected file is missing: {rel}",
                    location=rel,
                )
            )
        elif os.path.isfile(path) and os.path.getsize(path) == 0:
            findings.append(
                Finding(
                    check="structure",
                    severity=Severity.HIGH,
                    message=f"file is empty: {rel}",
                    location=rel,
                )
            )
    return CheckResult(name="structure", ok=not findings, findings=findings)
