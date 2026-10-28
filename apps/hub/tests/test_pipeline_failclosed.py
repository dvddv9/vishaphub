"""Fail-closed rules: an empty, unknown or crashed run must never read as a pass."""
import pytest

from hub.pipeline import MAX_ITERATIONS, MAX_MATERIAL, run_plan
from hub.router import Plan, Stage, plan_for

GOOD = {
    "calc/__init__.py": "def add(a, b):\n    return a + b\n",
    "test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
}
SPEC = {"entry": "calc", "files": ["calc/__init__.py", "test_calc.py"],
        "exports": ["add"], "tests": ["test_calc.py"]}


def stub_validator(monkeypatch, report):
    monkeypatch.setattr("hub.local.validate_code", lambda *a, **k: {"ok": True, "report": report})


def stub_analyser(monkeypatch, result):
    monkeypatch.setattr("hub.local.analyse_static", lambda *a, **k: result)


# 1. missing verdict ---------------------------------------------------------

def test_validator_without_a_verdict_fails_closed(monkeypatch):
    stub_validator(monkeypatch, {"finding_count": 0})
    result = run_plan(plan_for("validate"), files=GOOD, spec=SPEC)
    assert result.ok is False
    assert result.verdict == "ERROR"
    assert "no verdict" in result.reason


def test_validator_with_an_empty_verdict_fails_closed(monkeypatch):
    stub_validator(monkeypatch, {"verdict": "   ", "finding_count": 0})
    result = run_plan(plan_for("validate"), files=GOOD, spec=SPEC)
    assert result.ok is False and result.verdict == "ERROR"


def test_analyser_without_a_verdict_fails_closed(monkeypatch):
    stub_analyser(monkeypatch, {"ok": True, "findings": []})
    result = run_plan(plan_for("analyse"), material="x = 1")
    assert result.ok is False and result.verdict == "ERROR"


# 2. nothing ran -------------------------------------------------------------

def test_plan_without_stages_fails_closed():
    result = run_plan(Plan(stages=()), material="x = 1")
    assert result.ok is False and result.verdict == "ERROR"
    assert "no stages" in result.reason


@pytest.mark.parametrize("iterations", [0, -1])
def test_zero_iterations_fails_closed(iterations):
    result = run_plan(Plan(stages=(Stage.ANALYSER,), iterations=iterations), material="x = 1")
    assert result.ok is False and result.verdict == "ERROR"
    assert "iterations" in result.reason


# 3. unknown and lower-case verdicts ----------------------------------------

@pytest.mark.parametrize("verdict,expected_ok,expected", [
    ("fail", False, "FAIL"),
    ("emergency", False, "EMERGENCY"),
    ("  safe  ", True, "SAFE"),
    ("PASS", True, "PASS"),
])
def test_verdicts_are_normalised(monkeypatch, verdict, expected_ok, expected):
    stub_validator(monkeypatch, {"verdict": verdict, "finding_count": 0})
    result = run_plan(plan_for("validate"), files=GOOD, spec=SPEC)
    assert result.verdict == expected
    assert result.ok is expected_ok


@pytest.mark.parametrize("verdict", ["BLOCKED", "maybe", "42"])
def test_unknown_verdicts_are_not_a_pass(monkeypatch, verdict):
    stub_validator(monkeypatch, {"verdict": verdict, "finding_count": 0})
    result = run_plan(plan_for("validate"), files=GOOD, spec=SPEC)
    assert result.ok is False and result.verdict == "ERROR"


# 4. emergency must outrank fail --------------------------------------------

def test_emergency_is_not_hidden_by_a_failing_validator(monkeypatch):
    stub_validator(monkeypatch, {"verdict": "FAIL", "finding_count": 2})
    stub_analyser(monkeypatch, {"ok": True, "verdict": "EMERGENCY", "findings": [{"rule": "CWE-89"}]})
    result = run_plan(plan_for("validate+analyse"), material="x", files=GOOD, spec=SPEC)
    assert result.verdict == "EMERGENCY"
    assert result.ok is False
    assert "emergency" in result.reason.lower()


# 5. internal errors are not echoed -----------------------------------------

def test_missing_error_key_is_a_controlled_error(monkeypatch):
    monkeypatch.setattr("hub.local.validate_code", lambda *a, **k: {"ok": False})
    result = run_plan(plan_for("validate"), files=GOOD, spec=SPEC)
    assert result.verdict == "ERROR"
    assert result.steps[0].detail == "an internal check failed; the run is not a pass"


def test_raw_error_text_is_not_returned_to_the_client(monkeypatch):
    secret = "sqlite3.OperationalError: /home/hub/.vishap/data/prod.db is locked"
    monkeypatch.setattr("hub.local.validate_code", lambda *a, **k: {"ok": False, "error": secret})
    result = run_plan(plan_for("validate"), files=GOOD, spec=SPEC)
    payload = str(result.as_dict())
    assert secret not in payload
    assert "/home/hub" not in payload


# 6. bounds ------------------------------------------------------------------

def test_oversized_material_is_refused():
    result = run_plan(plan_for("analyse"), material="x" * (MAX_MATERIAL + 1))
    assert result.ok is False and result.verdict == "ERROR"
    assert "material above" in result.reason


def test_too_many_files_are_refused(monkeypatch):
    files = {f"f{i}.py": "x = 1\n" for i in range(201)}
    result = run_plan(plan_for("validate"), files=files, spec=SPEC)
    assert result.ok is False and "files is refused" in result.reason


def test_too_many_iterations_are_refused():
    result = run_plan(Plan(stages=(Stage.ANALYSER,), iterations=MAX_ITERATIONS + 1), material="x")
    assert result.ok is False and "iterations above" in result.reason
