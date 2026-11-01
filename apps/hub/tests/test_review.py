"""Review: the model reads the material, the rules check it, the stricter verdict wins.

The model is always faked here: nothing spends a token or needs a key. What these tests pin is the contract a
person relies on - the model can raise a verdict and add findings, it can never remove what the rules found, and a
model that cannot answer does not take the rules' answer down with it.
"""
from hub import local, proposal
from hub.pipeline import run_plan
from hub.router import Stage, plan_for

CODE = "cur.execute(\"select * from t where a = \" + x)\n"
RULES_FOUND = {"ok": True, "verdict": "REQUIRES_REVIEW", "reason": "1 finding(s); worst severity critical",
               "findings": [{"severity": "critical", "rule": "sqli-fstring", "line": 1}], "meaning": ""}
RULES_QUIET = {"ok": True, "verdict": "REQUIRES_REVIEW", "reason": "unknown coverage: no passing measurement",
               "findings": [], "meaning": "not a statement that nothing is wrong"}
MODEL_FINDING = {"severity": "high", "rule": "CWE-22", "message": "path traversal in send_file", "line": 14}


def fake(**over):
    payload = {"ok": True, "model": "test-model", "verdict": "SAFE", "findings": [],
               "patch": {}, "questions": [], "proof": [], "summary": "reads fine"}
    payload.update(over)
    return payload


def review(monkeypatch, model, rules, **kw):
    monkeypatch.setattr(proposal, "propose", lambda **k: model)
    monkeypatch.setattr(local, "analyse_static", lambda text, model_verdict="": rules)
    return run_plan(plan_for("review"), material=CODE, question="is this safe?", api_key="k", **kw)


def test_a_review_is_the_model_then_the_rules_with_no_validator():
    plan = plan_for("review")
    assert plan.stages == (Stage.GENERATOR, Stage.ANALYSER)
    assert plan.iterations == 1 and plan.partial and plan.model_optional
    assert "stricter verdict wins" in plan.note
    assert plan_for("generate+analyse").model_optional is False        # generation still needs its model


def test_what_the_model_adds_and_what_the_rules_found_are_both_shown_and_told_apart(monkeypatch):
    result = review(monkeypatch, fake(verdict="REQUIRES_REVIEW", findings=[MODEL_FINDING]), RULES_FOUND)
    by_source = {f["source"]: f for f in result.findings}
    assert by_source["model"]["rule"] == "CWE-22"           # the traversal the rules missed
    assert by_source["material"]["rule"] == "sqli-fstring"   # the injection the rules caught
    assert result.model_verdict == "REQUIRES_REVIEW" and result.rules_verdict == "REQUIRES_REVIEW"
    assert any("no validator" in line for line in result.not_checked)


def test_a_model_that_says_safe_cannot_clear_what_the_rules_found(monkeypatch):
    result = review(monkeypatch, fake(verdict="SAFE"), RULES_FOUND)
    assert result.verdict == "REQUIRES_REVIEW" and result.model_verdict == "SAFE"
    assert [f["rule"] for f in result.findings] == ["sqli-fstring"]


def test_a_model_that_says_safe_does_not_turn_unmeasured_rules_into_safe(monkeypatch):
    result = review(monkeypatch, fake(verdict="SAFE"), RULES_QUIET)
    assert result.verdict == "REQUIRES_REVIEW" and result.ok


def test_a_model_that_sees_danger_raises_the_verdict_and_the_run_says_so(monkeypatch):
    result = review(monkeypatch, fake(verdict="EMERGENCY"), RULES_QUIET)
    assert result.verdict == "EMERGENCY" and not result.ok
    assert "the model rated the risk higher than the rules did" in result.reason


def test_a_model_that_cannot_answer_does_not_take_the_rules_answer_with_it(monkeypatch):
    refused = {"ok": False, "error": "model refused: HTTP 401 {\"type\":\"error\",\"request_id\":\"req_1\"}"}
    result = review(monkeypatch, refused, RULES_FOUND)
    assert result.verdict == "REQUIRES_REVIEW" and result.ok                # the rules' own answer, not an ERROR
    assert [f["rule"] for f in result.findings] == ["sqli-fstring"]
    assert "your model key was rejected by Anthropic" in result.reason
    assert any("the model's reading is missing" in line for line in result.not_checked)
    assert "request_id" not in result.reason and all("request_id" not in line for line in result.not_checked)


def test_a_review_with_nothing_to_review_is_still_an_error_not_a_pass(monkeypatch):
    monkeypatch.setattr(proposal, "propose", lambda **k: {"ok": False, "error": "no model key: set one"})
    result = run_plan(plan_for("review"), material="", question="is this safe?", api_key="")
    assert result.verdict == "ERROR" and not result.ok


def test_generation_without_its_model_is_still_an_error(monkeypatch):
    monkeypatch.setattr(proposal, "propose", lambda **k: {"ok": False, "error": "model refused: HTTP 401"})
    monkeypatch.setattr(local, "analyse_static", lambda text, model_verdict="": RULES_FOUND)
    result = run_plan(plan_for("generate+analyse"), material=CODE, question="fix it", api_key="k")
    assert result.verdict == "ERROR" and not result.ok                  # review is the only mode with a soft model


def test_a_finding_both_readers_saw_is_one_finding_and_the_run_says_how_much_they_overlapped(monkeypatch):
    rules = {**RULES_FOUND, "findings": [{"severity": "critical", "rule": "sqli-fstring", "line": 1, "cwe": "CWE-89",
                                          "message": "SQL built with an f-string", "fix": "bind parameters"}]}
    model = fake(verdict="REQUIRES_REVIEW", findings=[{"severity": "critical", "rule": "CWE-89", "message": "injection", "line": 1}])
    result = review(monkeypatch, model, rules)
    assert len(result.findings) == 1 and result.findings[0]["seen_by"] == ["rules", "model"]
    assert result.agreement == {"both": 1, "model_only": 0, "rules_only": 0, "in_patch": 0}
    assert result.as_dict()["agreement"]["both"] == 1


def test_one_reader_alone_has_nothing_to_agree_with(monkeypatch):
    monkeypatch.setattr(local, "analyse_static", lambda text, model_verdict="": RULES_FOUND)
    rules_only = run_plan(plan_for("analyse"), material=CODE)
    assert rules_only.agreement == {} and rules_only.findings[0]["seen_by"] == ["rules"]
    monkeypatch.setattr(proposal, "propose", lambda **k: fake(verdict="REQUIRES_REVIEW", findings=[MODEL_FINDING]))
    model_only = run_plan(plan_for("ask"), question="what is wrong?", material=CODE, api_key="k")
    assert model_only.agreement == {} and model_only.findings[0]["seen_by"] == ["model"]
