"""Syntax check: every Python file in the deliverable must parse.

A file that does not parse cannot be trusted to behave, so this check runs before
behaviour and stops the run when it fails.
"""
from __future__ import annotations

import ast
import os

from ..models import CheckResult, Finding, Severity, Spec

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "out", "dist", "build"}


def _python_files(root: str) -> list[str]:
    found: list[str] = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if name.endswith(".py"):
                found.append(os.path.join(dirpath, name))
    return found


def run(root: str, spec: Spec) -> CheckResult:
    findings: list[Finding] = []
    files = _python_files(root)
    if not files:
        return CheckResult(
            name="syntax",
            ok=True,
            skipped=True,
            skip_reason="no Python files in the deliverable",
        )
    for path in files:
        rel = os.path.relpath(path, root)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                ast.parse(fh.read(), filename=rel)
        except SyntaxError as exc:
            findings.append(
                Finding(
                    check="syntax",
                    severity=Severity.CRITICAL,
                    message=f"syntax error: {exc.msg}",
                    location=f"{rel}:{exc.lineno or 0}",
                )
            )
    return CheckResult(name="syntax", ok=not findings, findings=findings)
