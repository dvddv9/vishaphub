"""Coverage check: is every public name actually exercised by the spec's tests?

Not line coverage — that needs the tests to run and pass, which is a later check.
This asks a cheaper and more honest question: does any test mention the name at all?
A public function nobody calls is either untested or not needed; either way it is a
divergence worth naming before behaviour is measured.
"""
from __future__ import annotations

import ast
import os

from ..models import CheckResult, Finding, Severity, Spec

SKIP_NAMES = {"main", "setup", "teardown"}


def _public_defs(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            tree = ast.parse(fh.read(), filename=path)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not node.name.startswith("_")
            and node.name not in SKIP_NAMES
        ):
            names.append(node.name)
    return names


def _test_text(root: str, spec: Spec) -> str:
    chunks: list[str] = []
    for rel in spec.tests:
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                chunks.append(fh.read())
    return "\n".join(chunks)


def run(root: str, spec: Spec) -> CheckResult:
    if not spec.tests:
        return CheckResult(name="coverage", ok=True, skipped=True,
                           skip_reason="no tests declared, nothing to measure")

    entry = spec.entry or ""
    module_dir = os.path.join(root, entry.replace(".", "/")) if entry else root
    if not os.path.isdir(module_dir):
        candidate = os.path.join(root, f"{entry}.py")
        module_dir = candidate if os.path.isfile(candidate) else root

    targets: list[tuple[str, str]] = []
    if os.path.isdir(module_dir):
        for name in sorted(os.listdir(module_dir)):
            if name.endswith(".py"):
                for public in _public_defs(os.path.join(module_dir, name)):
                    targets.append((name, public))
    elif os.path.isfile(module_dir):
        for public in _public_defs(module_dir):
            targets.append((os.path.basename(module_dir), public))

    if not targets:
        return CheckResult(name="coverage", ok=True, skipped=True,
                           skip_reason="no public definitions found")

    text = _test_text(root, spec)
    findings: list[Finding] = []
    for where, name in targets:
        if name not in text:
            findings.append(
                Finding(
                    check="coverage",
                    severity=Severity.MEDIUM,
                    message=f"public name is never mentioned by the tests: {name}",
                    location=where,
                )
            )
    return CheckResult(name="coverage", ok=not findings, findings=findings)
