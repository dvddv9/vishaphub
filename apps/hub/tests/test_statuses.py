"""Three results, three questions: risk verdict, fix status, verification status."""
import pytest

from hub import pipeline, statuses, templates
from hub.router import plan_for


def compute(**over):
    base = {"ok": True, "verdict": "REQUIRES_REVIEW", "checks": {"analyser": {"verdict": "REQUIRES_REVIEW"}},
            "plan": {"stages": ["analyser"], "partial": True}, "patch": {}, "model_verdict": "",
            "not_checked": []}
    base.update(over)
    return statuses.compute(**base)


def test_no_patch_and_a_patch_that_was_not_checked_are_different_statuses():
    assert compute()["fix"]["status"] == "NO_PATCH"
    one = compute(patch={"a.py": "x = 1"})["fix"]
    assert one["status"] == "FIX_UNVERIFIED" and "not applied" in one["reason"]


@pytest.mark.parametrize("fix_status", statuses.FIX_STATUSES)
@pytest.mark.parametrize("verdict", ["SAFE", "REQUIRES_REVIEW", "FAIL", "EMERGENCY"])
def test_a_fix_status_never_changes_the_risk_verdict(verdict, fix_status):
    out = compute(verdict=verdict, patch={"a.py": "x"}, patch_check={"status": fix_status, "reason": "r"})
    assert out["risk"]["verdict"] == verdict
    assert out["fix"]["status"] == fix_status


def test_an_unknown_fix_status_is_refused_not_shown():
    with pytest.raises(ValueError):
        compute(patch={"a.py": "x"}, patch_check={"status": "FIXED_FOR_SURE"})


def test_the_verdict_names_what_it_rests_on_and_a_model_alone_is_a_guess():
    both = compute(checks={"analyser": {"verdict": "SAFE"}, "validator": {"verdict": "PASS"}},
                   verdict="PASS", model_verdict="SAFE")["risk"]
    assert both["basis"] == {"rules": "SAFE", "tests": "PASS", "model": "SAFE"}
    assert both["rests_on_model_alone"] is False
    alone = compute(checks={}, verdict="REQUIRES_REVIEW", model_verdict="REQUIRES_REVIEW")["risk"]
    assert alone["rests_on_model_alone"] is True


def test_verification_says_how_much_of_the_plan_really_ran():
    full = compute(checks={"analyser": {"verdict": "SAFE"}, "validator": {"verdict": "PASS"}},
                   plan={"stages": ["validator", "analyser"]})["verification"]
    assert full["status"] == "COMPLETE" and full["not_run"] == []
    only = compute()["verification"]
    assert only["status"] == "PARTIAL" and only["ran"] == ["analyser"]
    skipped = compute(checks={"analyser": {"verdict": "SAFE"}}, plan={"stages": ["validator", "analyser"]})["verification"]
    assert skipped["status"] == "PARTIAL" and skipped["not_run"] == ["validator"]
    assert compute(checks={}, plan={"stages": ["validator"]})["verification"]["status"] == "NOT_RUN"
    assert compute(checks={}, verdict="ERROR")["verification"]["status"] == "ERROR"


def test_the_validator_isolation_travels_into_the_verification_status():
    iso = {"kind": "container", "cleanup_confirmed": True}
    out = compute(checks={"validator": {"verdict": "PASS", "isolation": iso}},
                  plan={"stages": ["validator"]})["verification"]
    assert out["isolation"] == iso


def test_a_real_run_carries_all_three_and_they_agree_with_the_top_level_verdict():
    data = pipeline.run_plan(plan_for("analyse"), material="cur.execute('select ' + x)").as_dict()
    st = data["statuses"]
    assert st["risk"]["verdict"] == data["verdict"]
    assert st["fix"]["status"] == "NO_PATCH"
    assert st["verification"]["status"] == "PARTIAL" and st["verification"]["ran"] == ["analyser"]


def test_the_report_page_shows_the_three_results_and_older_runs_still_render():
    data = pipeline.run_plan(plan_for("analyse"), material="x = 1").as_dict()
    html = templates.report_page({"id": "abc", "result": data, "verdict": data["verdict"]})
    for word in ("Three results", "risk verdict", "fix status", "verification", "NO_PATCH", "PARTIAL"):
        assert word in html
    old = dict(data)
    del old["statuses"]
    assert "Three results" not in templates.report_page({"id": "abc", "result": old, "verdict": data["verdict"]})