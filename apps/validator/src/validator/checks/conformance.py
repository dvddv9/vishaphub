"""Conformance check: is the promised code real, or a placeholder wearing a name?

A function that returns ``None`` and says ``pass`` imports fine and may even pass a
test that only checks existence. The promise was behaviour, so a stub is a
divergence — and the cheapest place to catch it is here, before anyone trusts it.
"""
from __future__ import annotations

import ast
import io
import os
import re
import tokenize

from ..models import CheckResult, Finding, Severity, Spec

PLACEHOLDER_CALLS = {"NotImplementedError", "NotImplemented"}
#: Markers are looked for in comments only, as whole words: `todos = []`, `stubborn` and a docstring that says
#: "not implemented in Python 2" are code, not placeholders. TODO / FIXME are the upper-case convention.
MARKER_PATTERNS = (
    ("TODO", re.compile(r"\bTODO\b")),
    ("FIXME", re.compile(r"\bFIXME\b")),
    ("not implemented", re.compile(r"\bnot implemented\b", re.IGNORECASE)),
    ("stub", re.compile(r"\bstubs?\b", re.IGNORECASE)),
)


def _markers(source: str) -> list[tuple[str, int]]:
    """(marker, line) for the first comment that carries each marker."""
    seen: dict[str, int] = {}
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT:
                continue
            for name, pattern in MARKER_PATTERNS:
                if name not in seen and pattern.search(token.string):
                    seen[name] = token.start[0]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return list(seen.items())


def _scan_file(path: str, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        tree = ast.parse(source, filename=rel)
    except SyntaxError:
        return findings  # the syntax check already owns this failure

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        # a docstring is a string constant expression; ``...`` is a constant too, and it
        # is the stub — so only strings are skipped here.
        body = [n for n in node.body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and isinstance(n.value.value, str))]
        # a lone pass / ... / raise NotImplementedError is a stub, not a function
        if len(body) == 1:
            only = body[0]
            if isinstance(only, ast.Pass):
                findings.append(Finding(check="conformance", severity=Severity.HIGH,
                                        message=f"public function is a stub (pass): {node.name}",
                                        location=f"{rel}:{node.lineno}"))
                continue
            if isinstance(only, ast.Expr) and isinstance(only.value, ast.Constant) and only.value.value is Ellipsis:
                findings.append(Finding(check="conformance", severity=Severity.HIGH,
                                        message=f"public function is a stub (...): {node.name}",
                                        location=f"{rel}:{node.lineno}"))
                continue
            if isinstance(only, ast.Raise) and isinstance(only.exc, ast.Name) and only.exc.id in PLACEHOLDER_CALLS:
                findings.append(Finding(check="conformance", severity=Severity.HIGH,
                                        message=f"public function raises {only.exc.id}: {node.name}",
                                        location=f"{rel}:{node.lineno}"))
                continue
            if isinstance(only, ast.Raise) and isinstance(only.exc, ast.Call):
                func = only.exc.func
                if isinstance(func, ast.Name) and func.id in PLACEHOLDER_CALLS:
                    findings.append(Finding(check="conformance", severity=Severity.HIGH,
                                            message=f"public function raises {func.id}: {node.name}",
                                            location=f"{rel}:{node.lineno}"))
                    continue

    for marker, line in _markers(source):
        findings.append(Finding(check="conformance", severity=Severity.LOW,
                                message=f"placeholder marker in the deliverable: {marker!r}",
                                location=f"{rel}:{line}"))
    return findings


def run(root: str, spec: Spec) -> CheckResult:
    targets: list[str] = []
    for rel in spec.files:
        path = os.path.join(root, rel)
        if os.path.isfile(path) and rel.endswith(".py"):
            targets.append(rel)

    if not targets:
        return CheckResult(name="conformance", ok=True, skipped=True,
                           skip_reason="no Python files declared in the spec")

    findings: list[Finding] = []
    for rel in targets:
        findings.extend(_scan_file(os.path.join(root, rel), rel))
    return CheckResult(name="conformance", ok=not findings, findings=findings)
