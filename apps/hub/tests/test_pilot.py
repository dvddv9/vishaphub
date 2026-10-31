"""The pilot's corpus and report: the corpus is what it claims to be, the expectations are well formed."""
import ast
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

pilot_cases = pytest.importorskip("pilot.cases")
run_pilot = pytest.importorskip("pilot.run_pilot")
report = pytest.importorskip("pilot.report")


def test_every_case_is_valid_python_and_its_test_imports_its_entry():
    for case in pilot_cases.CASES:
        ast.parse(case["app"])
        ast.parse(pilot_cases.TESTS[case["class"]])
        entry = pilot_cases.TARGETS[case["class"]]["entry"].split(":")[1]
        assert f"def {entry}(" in case["app"], case["id"]


def test_each_class_has_vulnerable_cases_and_a_safe_twin_to_fix_with():
    for kind in pilot_cases.TARGETS:
        members = [c for c in pilot_cases.CASES if c["class"] == kind]
        assert any(c["vulnerable"] for c in members) and any(not c["vulnerable"] for c in members)
        twin = pilot_cases.by_id(pilot_cases.FIX_WITH[kind])
        assert twin["class"] == kind and twin["vulnerable"] is False


def test_the_expectations_are_written_for_cases_that_exist_and_use_known_statuses():
    ids = {c["id"] for c in pilot_cases.CASES}
    plan = run_pilot.scenarios()
    assert len(plan) >= 30
    for s in plan:
        assert s["case"] in ids and s["expect"] in (run_pilot.V, run_pilot.P, run_pilot.R, run_pilot.U)
        assert pilot_cases.by_id(s["case"])["vulnerable"] is True      # a patch is proposed only where there is something to fix


def test_the_rules_only_pilot_runs_without_docker_and_executes_nothing(tmp_path):
    out = tmp_path / "r.json"
    assert run_pilot.main(["--rules-only", "--out", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["meta"]["model_called"] is False and result["meta"]["executed_code"] == "none"
    assert len(result["corpus_rules"]) == len(pilot_cases.CASES)
    assert {c["outcome"] for c in result["corpus_rules"]} <= {"TP", "FN", "FP", "TN"}
    assert "probes" not in result and "scenarios" not in result


def test_the_report_is_built_from_the_json_and_never_claims_automatic_fixing():
    result = {"digest": "d" * 64, "meta": {"model_called": False, "image": "x", "python": "3", "date": "d"},
              "corpus_rules": [{"case": "a", "class": "sqli", "vulnerable": True, "flagged_by": ["r"], "outcome": "TP"}],
              "sandbox_failures": []}
    text = report.build(result)
    assert "model_called: false" in text and "TP" in text and "does not show" in text
    assert "automatically" in text and "no claim" in text