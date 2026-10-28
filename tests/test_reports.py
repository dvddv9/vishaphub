"""Reports: the strictest verdict survives, and conditions are never dropped."""
from core.reports import Evidence, Level, Report, strictest


def test_strictest_of_empty_is_safe():
    assert strictest([]) is Level.SAFE


def test_strictest_takes_the_worst_not_the_last():
    assert strictest([Level.SAFE, Level.FAIL, Level.NEEDS_REVIEW]) is Level.FAIL


def test_error_outranks_fail():
    assert strictest([Level.FAIL, Level.ERROR]) is Level.ERROR


def test_merge_keeps_both_sides_evidence():
    analyser = Report("analyser", Level.NEEDS_REVIEW, findings=[Evidence("cwe", "CWE-89", "a.py:3")])
    validator = Report("validator", Level.SAFE, findings=[Evidence("structure", "ok", "")])
    merged = analyser.merge(validator)
    assert merged.level is Level.NEEDS_REVIEW
    assert len(merged.findings) == 2


def test_merge_keeps_conditions_from_both():
    first = Report("a", Level.SAFE, conditions=["material is Python"])
    second = Report("b", Level.SAFE, conditions=["coverage is measured"])
    merged = first.merge(second)
    assert merged.conditions == ["material is Python", "coverage is measured"]


def test_partial_flag_survives_merge():
    merged = Report("a", Level.SAFE).merge(Report("b", Level.SAFE, partial=True))
    assert merged.partial is True


def test_markdown_says_partial_is_not_a_proof():
    text = Report("run", Level.SAFE, partial=True).to_markdown()
    assert "not a proof" in text


def test_markdown_lists_findings_with_location():
    text = Report("run", Level.FAIL, findings=[Evidence("cwe", "CWE-89", "a.py:3")]).to_markdown()
    assert "CWE-89" in text and "a.py:3" in text


def test_markdown_lists_conditions():
    text = Report("run", Level.SAFE, conditions=["material is Python"]).to_markdown()
    assert "True under" in text and "material is Python" in text
