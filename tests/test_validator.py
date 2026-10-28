"""Validator: each check answers one question, and the verdict never over-claims."""
import json
import os

import pytest

from validator.checks import behavior, contract, structure, syntax
from validator.engine import validate
from validator.models import Severity, Spec, Verdict


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


@pytest.fixture
def good(tmp_path):
    root = tmp_path / "good"
    write(root / "calc" / "__init__.py", "def add(a, b):\n    return a + b\n")
    write(root / "test_calc.py", "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    return str(root)


# structure ------------------------------------------------------------------

def test_structure_passes_when_files_exist(good):
    result = structure.run(good, Spec(files=["calc/__init__.py", "test_calc.py"]))
    assert result.ok is True


def test_structure_reports_a_missing_file(good):
    result = structure.run(good, Spec(files=["missing.py"]))
    assert result.ok is False
    assert result.findings[0].severity is Severity.CRITICAL


def test_structure_reports_an_empty_file(good, tmp_path):
    write(os.path.join(good, "empty.py"), "")
    result = structure.run(good, Spec(files=["empty.py"]))
    assert result.ok is False
    assert result.findings[0].severity is Severity.HIGH


# syntax ---------------------------------------------------------------------

def test_syntax_passes_on_valid_python(good):
    assert syntax.run(good, Spec()).ok is True


def test_syntax_fails_on_a_broken_file(good):
    write(os.path.join(good, "broken.py"), "def add(a, b)\n    return a + b\n")
    result = syntax.run(good, Spec())
    assert result.ok is False
    assert "syntax error" in result.findings[0].message


def test_syntax_skips_when_there_is_no_python(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = syntax.run(str(empty), Spec())
    assert result.skipped is True


def test_syntax_catches_a_bom(tmp_path):
    path = tmp_path / "bom.py"
    path.write_bytes("\ufeffx = 1\n".encode("utf-8"))
    result = syntax.run(str(tmp_path), Spec())
    assert result.ok is False


# contract -------------------------------------------------------------------

def test_contract_passes_when_names_are_importable(good):
    result = contract.run(good, Spec(entry="calc", exports=["add"]))
    assert result.ok is True


def test_contract_reports_a_missing_name(good):
    result = contract.run(good, Spec(entry="calc", exports=["subtract"]))
    assert result.ok is False
    assert "subtract" in result.findings[0].message


def test_contract_reports_an_unimportable_entry(good):
    result = contract.run(good, Spec(entry="nope", exports=["add"]))
    assert result.ok is False
    assert "does not import" in result.findings[0].message


def test_contract_skips_without_exports(good):
    assert contract.run(good, Spec()).skipped is True


# behaviour ------------------------------------------------------------------

def test_behaviour_passes_when_tests_pass(good):
    assert behavior.run(good, Spec(tests=["test_calc.py"])).ok is True


def test_behaviour_fails_when_a_test_fails(good):
    write(os.path.join(good, "test_calc.py"), "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 6\n")
    result = behavior.run(good, Spec(tests=["test_calc.py"]))
    assert result.ok is False
    assert result.findings[0].severity is Severity.HIGH


def test_behaviour_reports_a_missing_test_file(good):
    result = behavior.run(good, Spec(tests=["nope.py"]))
    assert result.ok is False
    assert "missing" in result.findings[0].message


def test_behaviour_leaves_the_deliverable_untouched(good):
    before = sorted(os.listdir(good))
    behavior.run(good, Spec(tests=["test_calc.py"]))
    assert sorted(os.listdir(good)) == before


# engine ---------------------------------------------------------------------

def test_engine_pass_on_a_clean_deliverable(good):
    report = validate(good, Spec(files=["calc/__init__.py", "test_calc.py"], entry="calc",
                                 exports=["add"], tests=["test_calc.py"]))
    assert report.verdict is Verdict.PASS


def test_engine_fails_and_stops_on_syntax(good):
    write(os.path.join(good, "broken.py"), "def x(\n")
    report = validate(good, Spec(files=["broken.py"], tests=["test_calc.py"]))
    assert report.verdict is Verdict.FAIL
    assert "stopped after syntax" in report.reason
    assert [c.name for c in report.checks] == ["structure", "syntax"]


def test_engine_marks_high_findings_as_needs_review(good):
    write(os.path.join(good, "test_calc.py"), "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 6\n")
    report = validate(good, Spec(tests=["test_calc.py"]))
    assert report.verdict is Verdict.NEEDS_REVIEW


def test_engine_error_is_never_pass(good, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr("validator.engine.behavior.run", boom)
    report = validate(good, Spec(tests=["test_calc.py"]))
    assert report.verdict is Verdict.ERROR


def test_report_serialises_to_json(good):
    report = validate(good, Spec(files=["calc/__init__.py"]))
    payload = json.loads(json.dumps(report.as_dict()))
    assert payload["verdict"] == "PASS"
    assert payload["finding_count"] == 0
