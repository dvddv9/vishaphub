"""One path: the model proposes, the rules decide, the strictest verdict wins.

These tests pin the merge of the two former mechanisms — the routed pipeline and the
single-pass run — into `run_plan`. The model is always faked: nothing here spends a
token or needs a key.
"""
import pytest

from hub import local, proposal
from hub.pipeline import run_plan
from hub.router import plan_for
from hub.verdicts import rank, strictest

SPEC = "name: demo\nentry: app.py\n"
GOOD = {
    "calc/__init__.py": "def add(a, b):\n    return a + b\n",
    "test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
}
VALIDATOR_SPEC = {"entry": "calc", "files": ["calc/__init__.py", "test_calc.py"],
                  "exports": ["add"], "tests": ["test_calc.py"]}
SQLI = "cur.execute(\"select * from t where a = \" + x)\n"


def fake(**over):
    payload = {"ok": True, "model": "test-model", "verdict": "SAFE", "findings": [],
               "patch": {}, "questions": [], "proof": [], "summary": "looks fine"}
    payload.update(over)
    return payload


# the merged order -------------------------------------------------------------

def test_one_ranking_for_the_whole_hub():
    assert strictest("SAFE", "PASS") == "SAFE"          # the same answer, different words
    assert strictest("SAFE", "REQUIRES_REVIEW") == "REQUIRES_REVIEW"
    assert strictest("NEEDS_REVIEW", "FAIL") == "FAIL"
    assert rank("EMERGENCY") > rank("FAIL")             # danger outranks a broken promise
    assert rank("ERROR") > rank("EMERGENCY")


# the model proposes -----------------------------------------------------------

def test_the_model_never_answers_without_a_key(monkeypatch):
    monkeypatch.delenv("VISHAP_HUB_LLM_KEY", raising=False)
    result = proposal.propose(material="x = 1")
    assert result["ok"] is False
    assert "no model key" in result["error"]


def test_an_unknown_model_verdict_becomes_a_doubt(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_LLM_KEY", "k")
    monkeypatch.setattr(proposal, "_call", lambda *a, **k: {
        "ok": True, "model": "m", "parsed": {"verdict": "probably fine"}, "text": "{}"})
    result = proposal.propose(material="x = 1")
    assert result["verdict"] == "REQUIRES_REVIEW"


# the rules decide ------------------------------------------------------------

def test_a_passing_model_cannot_soften_a_failing_test(monkeypatch):
    monkeypatch.setattr(proposal, "propose", lambda **kw: fake(verdict="SAFE"))
    monkeypatch.setattr(local, "validate_code", lambda files, spec: {
        "ok": True, "report": {"verdict": "FAIL", "finding_count": 2}})
    result = run_plan(plan_for("generate+validate"), files=GOOD, spec=VALIDATOR_SPEC,
                      api_key="k")
    assert result.verdict == "FAIL"
    assert result.model_verdict == "SAFE"
    assert result.rules_verdict == "FAIL"


def test_a_suspicious_model_can_raise_the_alarm(monkeypatch):
    monkeypatch.setattr(proposal, "propose", lambda **kw: fake(verdict="EMERGENCY"))
    monkeypatch.setattr(local, "validate_code", lambda files, spec: {
        "ok": True, "report": {"verdict": "PASS", "finding_count": 0}})
    result = run_plan(plan_for("generate+validate"), files=GOOD, spec=VALIDATOR_SPEC,
                      api_key="k")
    assert result.verdict == "EMERGENCY"
    assert result.ok is False
    assert "the model saw danger" in result.reason


# generated code is checked like any other code --------------------------------

def test_the_proposed_patch_goes_through_the_validator(monkeypatch):
    seen = {}

    def validate(files, spec):
        seen.update(files)
        return {"ok": True, "report": {"verdict": "PASS", "finding_count": 0}}

    monkeypatch.setattr(proposal, "propose", lambda **kw: fake(patch={"app.py": "print(1)\n"}))
    monkeypatch.setattr(local, "validate_code", validate)
    result = run_plan(plan_for("generate+validate"), spec=SPEC, api_key="k")
    assert seen == {"app.py": "print(1)\n"}
    assert [s.stage for s in result.steps] == ["generator", "validator"]
    assert result.verdict == "PASS"


def test_the_proposed_patch_goes_through_the_analyser(monkeypatch):
    monkeypatch.setattr(proposal, "propose", lambda **kw: fake(patch={"app.py": SQLI}))
    result = run_plan(plan_for("generate+analyse"), spec=SPEC, api_key="k")
    analyser = result.checks["analyser"]
    assert analyser["verdict"] == "REQUIRES_REVIEW"
    assert any(f.get("source") == "patch:app.py" for f in analyser["findings"])


def test_material_and_patch_are_both_analysed(monkeypatch):
    monkeypatch.setattr(proposal, "propose", lambda **kw: fake(patch={"app.py": "x = 1\n"}))
    result = run_plan(plan_for("generate+analyse"), material=SQLI, spec=SPEC, api_key="k")
    sources = {f.get("source") for f in result.checks["analyser"]["findings"]}
    assert "material" in sources
    assert "patch:app.py" not in sources


# one plan, one answer ---------------------------------------------------------

def test_an_explicit_files_argument_beats_the_proposed_patch(monkeypatch):
    monkeypatch.setattr(proposal, "propose", lambda **kw: fake(patch={"other.py": "y = 2\n"}))
    monkeypatch.setattr(local, "validate_code", lambda files, spec: {
        "ok": True, "report": {"verdict": "PASS", "finding_count": 0}})
    result = run_plan(plan_for("generate+validate"), files=GOOD, spec=VALIDATOR_SPEC, api_key="k")
    assert result.verdict == "PASS"
    assert result.patch == {"other.py": "y = 2\n"}       # still reported to the client


def test_the_generator_runs_once_and_later_passes_recheck(monkeypatch):
    calls = {"n": 0}

    def propose(**kw):
        calls["n"] += 1
        return fake()

    monkeypatch.setattr(proposal, "propose", propose)
    monkeypatch.setattr(local, "validate_code", lambda files, spec: {
        "ok": True, "report": {"verdict": "PASS", "finding_count": 0}})
    result = run_plan(plan_for("generate+validate", 3), files=GOOD, spec=VALIDATOR_SPEC, api_key="k")
    assert calls["n"] == 1
    assert any("reused the pass 1 proposal" in line for line in result.trace)


def test_a_question_without_material_is_answered_by_the_model_alone(monkeypatch):
    monkeypatch.setattr(proposal, "propose", lambda **kw: fake(summary="it depends"))
    result = run_plan(plan_for("ask"), question="what is this?", api_key="k")
    assert result.verdict == "SAFE"
    assert result.summary == "it depends"
    assert result.plan["partial"] is True


def test_a_run_with_nothing_to_check_is_an_error():
    result = run_plan(plan_for("analyse"))
    assert result.verdict == "ERROR"
    assert "needs material" in result.reason
