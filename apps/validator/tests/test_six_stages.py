"""The last two stages: coverage and conformance, plus six-stage order."""
import os

import pytest

from validator.checks import conformance, coverage
from validator.engine import ORDER, validate
from validator.models import Severity, Spec, Verdict


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "p"
    write(root / "calc" / "__init__.py", "def add(a, b):\n    return a + b\n")
    write(root / "test_calc.py", "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    return str(root)


def test_six_stages_in_order():
    assert [m.__name__.rsplit(".", 1)[-1] for m in ORDER] == [
        "structure", "syntax", "contract", "coverage", "behavior", "conformance"]


# coverage -------------------------------------------------------------------

def test_coverage_passes_when_the_name_is_mentioned(project):
    assert coverage.run(project, Spec(entry="calc", tests=["test_calc.py"])).ok is True


def test_coverage_flags_an_unexercised_public_name(project):
    write(os.path.join(project, "calc", "__init__.py"),
          "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n")
    result = coverage.run(project, Spec(entry="calc", tests=["test_calc.py"]))
    assert result.ok is False
    assert any("subtract" in f.message for f in result.findings)
    assert result.findings[0].severity is Severity.MEDIUM


def test_coverage_skips_without_tests(project):
    assert coverage.run(project, Spec()).skipped is True


def test_coverage_skips_when_nothing_public(project):
    write(os.path.join(project, "calc", "__init__.py"), "def _hidden():\n    return 1\n")
    assert coverage.run(project, Spec(entry="calc", tests=["test_calc.py"])).skipped is True


def test_coverage_does_not_flag_dunder_all(project):
    write(os.path.join(project, "calc", "__init__.py"), "__all__ = ['add']\n\n\ndef add(a, b):\n    return a + b\n")
    assert coverage.run(project, Spec(entry="calc", tests=["test_calc.py"])).ok is True


# conformance ----------------------------------------------------------------

def test_conformance_passes_on_real_code(project):
    assert conformance.run(project, Spec(files=["calc/__init__.py"])).ok is True


@pytest.mark.parametrize("body,needle", [
    ("    pass\n", "stub (pass)"),
    ("    ...\n", "stub (...)"),
    ("    raise NotImplementedError\n", "NotImplementedError"),
])
def test_conformance_flags_stubs(project, body, needle):
    write(os.path.join(project, "calc", "__init__.py"), f"def add(a, b):\n{body}")
    result = conformance.run(project, Spec(files=["calc/__init__.py"]))
    assert result.ok is False
    assert any(needle in f.message for f in result.findings)


def test_conformance_flags_placeholder_markers(project):
    write(os.path.join(project, "calc", "__init__.py"), "def add(a, b):\n    # TODO: real sum\n    return a + b\n")
    result = conformance.run(project, Spec(files=["calc/__init__.py"]))
    assert any(f.severity is Severity.LOW for f in result.findings)


def test_conformance_skips_without_declared_files(project):
    assert conformance.run(project, Spec()).skipped is True


# end to end ----------------------------------------------------------------

def test_full_run_is_pass(project):
    report = validate(project, Spec(files=["calc/__init__.py", "test_calc.py"], entry="calc",
                                    exports=["add"], tests=["test_calc.py"]))
    assert report.verdict is Verdict.PASS
    assert len(report.checks) == 6


def test_a_stub_deliverable_is_not_a_pass(project):
    write(os.path.join(project, "calc", "__init__.py"), "def add(a, b):\n    pass\n")
    report = validate(project, Spec(files=["calc/__init__.py"], entry="calc", tests=["test_calc.py"]))
    assert report.verdict in (Verdict.NEEDS_REVIEW, Verdict.FAIL)
