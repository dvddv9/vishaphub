"""The files returned as final are the files the hub checks, at a bounded model cost."""

from hub import local, proposal, templates
from hub.pipeline import run_plan
from hub.router import plan_for


def test_final_files_are_checked_and_not_regenerated_on_later_passes(monkeypatch):
    model_calls = []
    def propose(**kwargs):
        question = kwargs["question"]
        model_calls.append(question)
        if question.startswith("Return the final complete files"):
            patch = {"final.py": "value = 'final'\n"}
        elif question.startswith("Return a corrected full-file version"):
            patch = {"corrected.py": "value = 'corrected'\n"}
        else:
            patch = {"initial.py": "value = 'generated'\n"}
        return {"ok": True, "model": "test-model", "verdict": "SAFE", "findings": [],
                "patch": patch, "questions": [], "proof": [], "summary": "complete"}

    scanned = []
    validated = []

    def analyse(source, *, model_verdict="", filename=""):
        scanned.append((filename, source))
        return {"ok": True, "verdict": "SAFE", "findings": [],
                "coverage": {"language": "python"}, "reason": "no matching rule"}

    def validate(files, spec):
        validated.append(dict(files))
        return {"ok": True, "report": {"verdict": "PASS", "checks": [], "finding_count": 0}}

    monkeypatch.setattr(proposal, "propose", propose)
    monkeypatch.setattr(local, "analyse_static", analyse)
    monkeypatch.setattr(local, "validate_code", validate)

    result = run_plan(
        plan_for("generate+validate+analyse", iterations=3),
        material="value = 'input'\n",
        spec={"files": ["final.py"]},
        api_key="test-key",
    ).as_dict()

    assert sum(question.startswith("Return the final complete files") for question in model_calls) == 1, (model_calls, result["trace"])
    assert "will run its analyser" in model_calls[2]
    assert "not verified again" not in model_calls[2]
    assert result["final_version"] == {"final.py": "value = 'final'\n"}
    assert result["checks"]["final_validator"]["verified"] is True
    assert result["checks"]["final_generator"]["verified"] is True
    assert any(name == "final.py" and "value = 'final'" in source for name, source in scanned)
    assert validated[-1] == {"final.py": "value = 'final'\n"}
    assert "analyser and Validator ran" in templates._evidence_block(result["fingerprint"])
