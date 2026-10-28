"""Hub: envelope, routing and the pipeline's honesty rules."""
import pytest

from hub.envelope import Envelope, Kind
from hub.pipeline import run_plan
from hub.router import CANONICAL_ORDER, MAX_ITERATIONS, RouteError, Stage, plan_for
from hub.services import ServiceConfig


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

def _cfg():
    return ServiceConfig(analyser_url="http://analyser", generator_url="http://generator", timeout=1)


def test_pipeline_stops_when_generation_has_no_spec():
    result = run_plan(_cfg(), plan_for("generate+validate"), material="x", spec="")
    assert result.verdict == "ERROR"
    assert "needs a spec" in result.reason


def test_pipeline_reports_generator_failure(monkeypatch):
    monkeypatch.setattr("hub.pipeline.generate", lambda *a, **k: {"ok": False, "error": "down"})
    result = run_plan(_cfg(), plan_for("generate+analyse"), material="x", spec="s")
    assert result.verdict == "ERROR"
    assert "generator failed" in result.reason


def test_pipeline_takes_the_strictest_verdict(monkeypatch):
    monkeypatch.setattr("hub.pipeline.generate", lambda *a, **k: {"ok": True, "out_dir": "/tmp/x"})
    monkeypatch.setattr("hub.pipeline.validate", lambda *a, **k: {
        "ok": True, "report": {"verdict": "PASS", "finding_count": 0}})
    monkeypatch.setattr("hub.pipeline.analyse", lambda *a, **k: {
        "ok": True, "verdict": "REQUIRES_REVIEW", "cwe_ids": ["CWE-89"]})
    result = run_plan(_cfg(), plan_for("generate+validate+analyse"), material="x", spec="s")
    assert result.verdict == "REQUIRES_REVIEW"
    assert result.ok is True


def test_pipeline_fail_beats_review(monkeypatch):
    monkeypatch.setattr("hub.pipeline.generate", lambda *a, **k: {"ok": True, "out_dir": "/tmp/x"})
    monkeypatch.setattr("hub.pipeline.validate", lambda *a, **k: {
        "ok": True, "report": {"verdict": "FAIL", "finding_count": 2}})
    monkeypatch.setattr("hub.pipeline.analyse", lambda *a, **k: {
        "ok": True, "verdict": "SAFE", "cwe_ids": []})
    result = run_plan(_cfg(), plan_for("generate+validate+analyse"), material="x", spec="s")
    assert result.verdict == "FAIL"
    assert result.ok is False


def test_pipeline_stops_when_no_stage_changes_its_verdict(monkeypatch):
    calls = {"generate": 0, "validate": 0, "analyse": 0}

    monkeypatch.setattr("hub.pipeline.generate", lambda *a, **k: (
        calls.__setitem__("generate", calls["generate"] + 1) or {"ok": True, "out_dir": "/tmp/x"}))
    monkeypatch.setattr("hub.pipeline.validate", lambda *a, **k: (
        calls.__setitem__("validate", calls["validate"] + 1) or {
            "ok": True, "report": {"verdict": "PASS", "finding_count": 0}}))
    monkeypatch.setattr("hub.pipeline.analyse", lambda *a, **k: (
        calls.__setitem__("analyse", calls["analyse"] + 1) or {
            "ok": True, "verdict": "SAFE", "cwe_ids": []}))

    result = run_plan(_cfg(), plan_for("generate+validate+analyse", 3), material="x", spec="s")
    # Two passes: the second one repeats the first, so the third would be waste.
    assert calls["analyse"] == 2
    assert calls["generate"] == 2
    assert any("no stage changed its verdict" in line for line in result.trace)
    assert result.verdict == "PASS"


def test_pipeline_marks_analyser_failure_as_error(monkeypatch):
    monkeypatch.setattr("hub.pipeline.analyse", lambda *a, **k: {"ok": False, "error": "timeout"})
    result = run_plan(_cfg(), plan_for("analyse"), material="x")
    assert result.verdict == "ERROR"
    assert "analyser failed" in result.reason


def test_pipeline_trace_records_every_stage(monkeypatch):
    monkeypatch.setattr("hub.pipeline.analyse", lambda *a, **k: {
        "ok": True, "verdict": "SAFE", "cwe_ids": []})
    result = run_plan(_cfg(), plan_for("analyse"), material="x")
    assert any("analyser" in line for line in result.trace)
