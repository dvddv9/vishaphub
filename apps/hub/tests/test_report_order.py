"""The order of a report: findings more than one reader saw come first. Only the order changes; nothing is hidden."""
from hub import templates


def finding(rule, severity, seen_by=None, **extra):
    f = {"rule": rule, "severity": severity, "message": f"m-{rule}", "line": 1}
    if seen_by is not None:
        f["seen_by"] = seen_by
    return {**f, **extra}


def page(*findings):
    return templates.report_page({"id": "r1", "at": "t", "verdict": "REQUIRES_REVIEW", "ok": True,
                                  "result": {"ok": True, "verdict": "REQUIRES_REVIEW", "findings": list(findings)}})


def order_of(html, *rules):
    return [rule for _, rule in sorted((html.index(f"{r}</li>") if f"{r}</li>" in html else html.index(f"{r} @"), r)
                                       for r in rules)]


def test_findings_two_readers_saw_come_first_then_by_severity_and_a_heading_tells_the_two_apart():
    html = page(finding("low-both", "low", ["rules", "model"]), finding("crit-one", "critical", ["rules"]),
                finding("high-one", "high", ["model"]), finding("crit-ext", "critical", ["rules", "external"]),
                finding("none", "high"))
    assert order_of(html, "low-both", "crit-one", "high-one", "crit-ext", "none") == [
        "crit-ext", "low-both", "crit-one", "high-one", "none"]       # a tie keeps the order found: high-one, none
    assert html.index("seen by more than one reader") < html.index("crit-ext") < html.index("seen by one reader")
    assert html.index("seen by one reader") < html.index("crit-one")


def test_no_heading_when_there_is_only_one_kind_and_nothing_is_dropped():
    html = page(finding("x", "low", ["rules"]), finding("y", "high", ["rules"]))
    assert "seen by more than one reader" not in html and "seen by one reader" not in html
    assert order_of(html, "x", "y") == ["y", "x"]
    everyone = page(finding("p", "low", ["rules"]), finding("q", "low", ["model"]), finding("r", "high", ["rules", "model"]))
    assert all(f"m-{r}" in everyone for r in "pqr")


def test_a_finding_about_the_models_patch_stays_in_its_own_block_after_the_rest():
    html = page(finding("mine", "low", ["rules"]), finding("patched", "critical", ["rules", "model"], in_patch=True))
    assert html.index("In the model") < html.index("patched") and html.index("mine") < html.index("In the model")