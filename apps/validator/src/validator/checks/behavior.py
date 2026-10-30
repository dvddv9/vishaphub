"""Behaviour check: the spec's tests must run and pass.

Runs pytest in a subprocess with a timeout, no network proxy tricks, and a clean
report. A test that errors is not "flaky" here — it is a divergence between what
the spec promised and what the code does.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

from ..models import CheckResult, Finding, Severity, Spec
from ..safe import clean_env

TIMEOUT_SECONDS = 120
TAIL_CHARS = 1500


def run(root: str, spec: Spec) -> CheckResult:
    if not spec.tests:
        return CheckResult(
            name="behavior",
            ok=True,
            skipped=True,
            skip_reason="spec declares no tests",
        )

    missing = [t for t in spec.tests if not os.path.exists(os.path.join(root, t))]
    if missing:
        return CheckResult(
            name="behavior",
            ok=False,
            findings=[
                Finding(
                    check="behavior",
                    severity=Severity.CRITICAL,
                    message=f"spec test file is missing: {t}",
                    location=t,
                )
                for t in missing
            ],
        )

    # An empty ini outside the deliverable: pytest must not inherit the config of
    # whatever project happens to sit above it, and the deliverable stays untouched.
    ini_path = os.path.join(tempfile.gettempdir(), f"vishap-validator-{os.getpid()}.ini")
    with open(ini_path, "w", encoding="utf-8") as fh:
        fh.write("[pytest]\n")
    env = clean_env()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *spec.tests, "-q", "--no-header", "--tb=short",
             "-p", "no:cacheprovider", "-c", ini_path],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="behavior",
            ok=False,
            findings=[
                Finding(
                    check="behavior",
                    severity=Severity.HIGH,
                    message=f"tests did not finish in {TIMEOUT_SECONDS} s",
                    location=", ".join(spec.tests),
                )
            ],
        )

    if proc.returncode == 0:
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        # Exit 0 also means "everything was skipped" or "nothing was collected into a failure". A promise
        # nobody checked is not a kept promise.
        if not re.search(r"\b[1-9]\d* passed\b", out):
            return CheckResult(
                name="behavior", ok=False,
                findings=[Finding(check="behavior", severity=Severity.HIGH,
                                  message=f"pytest exited 0 but no test passed (all skipped?): {out[-TAIL_CHARS:]}",
                                  location=", ".join(spec.tests))])
        return CheckResult(name="behavior", ok=True)

    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()
    tail = tail[-TAIL_CHARS:]
    return CheckResult(
        name="behavior",
        ok=False,
        findings=[
            Finding(
                check="behavior",
                severity=Severity.HIGH,
                message=f"pytest failed with exit {proc.returncode}: {tail}",
                location=", ".join(spec.tests),
            )
        ],
    )
