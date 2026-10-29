"""Hub: envelope, routing and the pipeline's honesty rules."""
import pytest

from hub.envelope import Envelope, Kind
from hub.pipeline import run_plan
from hub.router import CANONICAL_ORDER, MAX_ITERATIONS, RouteError, Stage, plan_for


# envelope -------------------------------------------------------------------

def test_envelope_rejects_unknown_participants():
    with pytest.raises(ValueError):
        Envelope.build("hub", "someone", Kind.QUESTION, {})


def test_hop_appends_to_trace_without_mutating():
    original = Envelope.build("client", "hub", Kind.QUESTION, {"text": "hi"})
    hopped = original.hop("routed")
    assert original.trace == []
    assert len(hopped.trace) == 1
    assert hopped.session_id == original.session_id


def test_envelope_serialises_kind_as_string():
    payload = Envelope.build("client", "hub", Kind.ANSWER, {}).as_dict()
    assert payload["kind"] == "answer"


# router ---------------------------------------------------------------------

def test_single_stage_is_partial():
    plan = plan_for("analyse")
    assert plan.stages == (Stage.ANALYSER,)
    assert plan.partial is True
    assert "not verified" in plan.note


def test_full_route_is_canonical_order():
    plan = plan_for("generate+validate+analyse")
    assert plan.stages == CANONICAL_ORDER
    assert plan.partial is False


def test_route_order_is_normalised_whatever_the_client_wrote():
    plan = plan_for("validate+analyse")
    assert plan.stages == (Stage.VALIDATOR, Stage.ANALYSER)


def test_iterations_are_capped():
    assert plan_for("generate+validate+analyse", 99).iterations == MAX_ITERATIONS


def test_single_stage_ignores_iterations():
    assert plan_for("analyse", 5).iterations == 1


def test_unknown_intent_raises():
    with pytest.raises(RouteError):
        plan_for("do something clever")


# pipeline -------------------------------------------------------------------

GOOD = {
    "calc/__init__.py": "def add(a, b):\n    return a + b\n",
    "test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
}
SPEC = {"entry": "calc", "files": ["calc/__init__.py", "test_calc.py"],
        "exports": ["add"], "tests": ["test_calc.py"]}


def test_pipeline_generator_refuses_without_a_key(monkeypatch):
    monkeypatch.delenv("VISHAP_HUB_LLM_KEY", raising=False)
    result = run_plan(plan_for("generate+validate"), material="x", files=GOOD, spec=SPEC)
    assert result.verdict == "ERROR"
    assert "no model key" in result.reason
    assert result.steps[0].stage == "generator"


def test_pipeline_needs_material_for_analysis():
    result = run_plan(plan_for("analyse"), material="")
    assert result.verdict == "ERROR"
    assert "needs material" in result.reason


def test_pipeline_needs_files_for_validation():
    result = run_plan(plan_for("validate"), files={})
    assert result.verdict == "ERROR"
    assert "needs files" in result.reason


def test_pipeline_validates_a_clean_deliverable():
    result = run_plan(plan_for("validate"), files=GOOD, spec=SPEC)
    assert result.verdict == "PASS"
    assert result.ok is True
    assert result.steps[0].stage == "validator"


def test_pipeline_analyses_the_material_in_process():
    result = run_plan(plan_for("analyse"), material="cur.execute(\"select * from t where a = \" + x)")
    assert result.verdict in ("SAFE", "REQUIRES_REVIEW")
    assert result.steps[0].stage == "analyser"


def test_pipeline_takes_the_strictest_verdict(monkeypatch):
    monkeypatch.setattr("hub.local.validate_code", lambda files, spec: {
        "ok": True, "report": {"verdict": "PASS", "finding_count": 0}})
    monkeypatch.setattr("hub.local.analyse_static", lambda material: {
        "ok": True, "verdict": "REQUIRES_REVIEW", "findings": []})
    result = run_plan(plan_for("validate+analyse"), material="x", files=GOOD, spec=SPEC)
    assert result.verdict == "REQUIRES_REVIEW"
    assert result.ok is True


def test_pipeline_fail_beats_review(monkeypatch):
    monkeypatch.setattr("hub.local.validate_code", lambda files, spec: {
        "ok": True, "report": {"verdict": "FAIL", "finding_count": 2}})
    monkeypatch.setattr("hub.local.analyse_static", lambda material: {
        "ok": True, "verdict": "SAFE", "findings": []})
    result = run_plan(plan_for("validate+analyse"), material="x", files=GOOD, spec=SPEC)
    assert result.verdict == "FAIL"
    assert result.ok is False


def test_pipeline_stops_when_no_stage_changes_its_verdict(monkeypatch):
    calls = {"n": 0}

    def validate(*_a, **_k):
        calls["n"] += 1
        return {"ok": True, "report": {"verdict": "PASS", "finding_count": 0}}

    monkeypatch.setattr("hub.local.validate_code", validate)
    monkeypatch.setattr("hub.local.analyse_static", lambda material: {
        "ok": True, "verdict": "SAFE", "findings": []})
    result = run_plan(plan_for("validate+analyse", 3), material="x", files=GOOD, spec=SPEC)
    assert calls["n"] == 2
    assert any("no stage changed its verdict" in line for line in result.trace)


def test_pipeline_marks_a_validator_crash_as_error(monkeypatch):
    monkeypatch.setattr("hub.local.validate_code", lambda *a, **k: {"ok": False, "error": "boom"})
    result = run_plan(plan_for("validate"), files=GOOD, spec=SPEC)
    assert result.verdict == "ERROR"
    assert "validator failed" in result.reason


def test_pipeline_trace_records_every_stage():
    result = run_plan(plan_for("analyse"), material="x = 1")
    assert any("analyser" in line for line in result.trace)
