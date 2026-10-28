"""Build checks: the part of Build that needs no LLM.

Takes the file plan from Design and the files as written (by an LLM later,
by hand today) and checks them before Verify:

  - every planned file is there, and nothing outside the plan;
  - Python files parse (ast.parse, always);
  - ruff passes, when ruff is installed; otherwise the check is
    reported as skipped, not as passed;
  - the test file has a test for each requirement it serves, named
    test_rN or test_rN_<anything>, found by name in the syntax tree
    (test_r1 is not satisfied by test_r10);
  - no test names a requirement that does not exist.

Every problem is collected; one bad file does not hide the others.
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
from dataclasses import dataclass

from generator.pipeline.design import DesignResult, FilePlan
from generator.pipeline.intake import Requirement

TEST_NAME_RE = re.compile(r"^test_r(\d+)(?:_\w+)?$")
RUFF_TIMEOUT = 30


@dataclass(frozen=True)
class FileCheck:
    path: str
    role: str
    syntax: str                 # ok | error | not-python
    lint: str                   # pass | fail | skipped | not-python
    lint_note: str
    tests_found: tuple[str, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "role": self.role,
            "syntax": self.syntax,
            "lint": self.lint,
            "lint_note": self.lint_note,
            "tests_found": list(self.tests_found),
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class BuildCheck:
    files: tuple[FileCheck, ...]
    errors: tuple[str, ...]     # plan-level: missing or extra files

    @property
    def ok(self) -> bool:
        return not self.errors and all(not f.errors for f in self.files)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "files": [f.to_dict() for f in self.files],
        }


def _lint(path: str, code: str) -> tuple[str, str]:
    ruff = shutil.which("ruff")
    if not ruff:
        return "skipped", "ruff is not installed"
    try:
        res = subprocess.run(
            [ruff, "check", "--quiet", "--stdin-filename", path, "-"],
            input=code, capture_output=True, text=True, timeout=RUFF_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return "fail", f"ruff did not finish in {RUFF_TIMEOUT}s"
    if res.returncode == 0:
        return "pass", ""
    return "fail", (res.stdout or res.stderr).strip()[:2000]


def _test_names(tree: ast.AST) -> tuple[str, ...]:
    names = [
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and TEST_NAME_RE.match(node.name)
    ]
    return tuple(sorted(set(names)))


def _check_file(plan: FilePlan, code: str, known_ids: set[str]) -> FileCheck:
    errors: list[str] = []
    if not plan.path.endswith(".py"):
        return FileCheck(plan.path, plan.role, "not-python", "not-python",
                         "", (), ())

    try:
        tree = ast.parse(code, filename=plan.path)
    except SyntaxError as e:
        errors.append(f"syntax error at line {e.lineno}: {e.msg}")
        return FileCheck(plan.path, plan.role, "error", "skipped",
                         "not linted: the file does not parse", (), tuple(errors))

    lint, note = _lint(plan.path, code)
    if lint == "fail":
        errors.append("ruff found problems")

    found: tuple[str, ...] = ()
    if plan.role == "test":
        found = _test_names(tree)
        covered = {f"R{TEST_NAME_RE.match(n).group(1)}" for n in found}
        for rid in plan.requirements:
            if rid not in covered:
                errors.append(f"no test for {rid} (expected test_{rid.lower()})")
        for rid in sorted(covered - known_ids, key=lambda r: int(r[1:])):
            errors.append(f"a test names {rid}, which is not a requirement")

    return FileCheck(plan.path, plan.role, "ok", lint, note, found, tuple(errors))


def check_build(design: DesignResult, requirements: tuple[Requirement, ...],
                files: dict[str, str]) -> BuildCheck:
    """`files` maps each path to its content."""
    planned = {f.path for f in design.files}
    errors = [f"missing file {p}" for p in sorted(planned - set(files))]
    errors += [f"file {p} is not in the plan" for p in sorted(set(files) - planned)]

    known = {r.id for r in requirements}
    checks = tuple(
        _check_file(plan, files[plan.path], known)
        for plan in design.files if plan.path in files
    )
    return BuildCheck(files=checks, errors=tuple(errors))
