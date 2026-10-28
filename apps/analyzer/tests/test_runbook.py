# -*- coding: utf-8 -*-
"""Tests for src/tools/runbook.py (P2-9).

Test-first: written BEFORE the module. Expect ImportError on first run.
"""
from src.tools.runbook import generate_runbook, enrich_runbook
from src.tools.patterns import RUNBOOKS


# --- generate_runbook ---

def test_generate_runbook_single_cwe():
    result = generate_runbook(["CWE-89"])
    assert "CWE-89" in result
    assert result["CWE-89"]["title"] == "SQL Injection"


def test_generate_runbook_multiple_cwes():
    result = generate_runbook(["CWE-89", "CWE-79"])
    assert set(result.keys()) == {"CWE-89", "CWE-79"}


def test_generate_runbook_empty():
    result = generate_runbook([])
    assert result == {}


def test_generate_runbook_unknown_cwe():
    result = generate_runbook(["CWE-9999"])
    assert result == {}


def test_generate_runbook_structure():
    result = generate_runbook(["CWE-89"])
    entry = result["CWE-89"]
    for key in ("title", "severity", "immediate", "short_term", "long_term", "escalation"):
        assert key in entry, f"missing key: {key}"


def test_generate_runbook_immediate_not_empty():
    result = generate_runbook(["CWE-89"])
    assert len(result["CWE-89"]["immediate"]) >= 1


# --- enrich_runbook ---

def test_enrich_runbook_backward_compat():
    result = enrich_runbook(["CWE-89"])
    assert "runbook" in result
    assert "CWE-89" in result["runbook"]


def test_enrich_runbook_new_fields():
    result = enrich_runbook(["CWE-89", "CWE-79"])
    assert "runbook" in result
    assert "runbook_cwes" in result
    assert "runbook_steps_count" in result
    assert set(result["runbook_cwes"]) == {"CWE-89", "CWE-79"}


def test_enrich_runbook_empty():
    result = enrich_runbook([])
    assert result["runbook"] == {}
    assert result["runbook_cwes"] == []
    assert result["runbook_steps_count"] == 0


def test_enrich_runbook_sorted_cwes():
    result = enrich_runbook(["CWE-79", "CWE-22"])
    # sorted alphabetically
    assert result["runbook_cwes"] == sorted(result["runbook_cwes"])


def test_enrich_runbook_does_not_mutate():
    cwes = ["CWE-89"]
    original = list(cwes)
    enrich_runbook(cwes)
    assert cwes == original


def test_enrich_runbook_steps_count():
    result = enrich_runbook(["CWE-89"])
    entry = RUNBOOKS["CWE-89"]
    expected = (
        len(entry["immediate"])
        + len(entry["short_term"])
        + len(entry["long_term"])
    )
    assert result["runbook_steps_count"] == expected


# --- RUNBOOKS data ---

def test_runbooks_has_min_10_cwes():
    assert len(RUNBOOKS) >= 10


def test_runbooks_cwe_89_structure():
    entry = RUNBOOKS["CWE-89"]
    assert entry["title"] == "SQL Injection"
    assert entry["severity"] == "critical"
    assert isinstance(entry["immediate"], list)
    assert isinstance(entry["short_term"], list)
    assert isinstance(entry["long_term"], list)


def test_runbooks_severity_values():
    valid = {"critical", "high", "medium", "low"}
    for cwe, entry in RUNBOOKS.items():
        assert entry["severity"] in valid, f"{cwe}: {entry['severity']}"


def test_runbook_escalation_string():
    for cwe, entry in RUNBOOKS.items():
        assert isinstance(entry["escalation"], str), f"{cwe} escalation not str"
        assert entry["escalation"], f"{cwe} escalation empty"
