# -*- coding: utf-8 -*-
"""Tests for src/tools/compliance.py (P2-8).

Test-first: written BEFORE the module. Expect ImportError on first run.
"""
from src.tools.compliance import map_compliance, enrich_compliance
from src.tools.patterns import COMPLIANCE_MAP


# --- map_compliance ---

def test_map_compliance_single_cwe_single_standard():
    result = map_compliance(["CWE-89"], standards=["PCI-DSS"])
    assert result == {"PCI-DSS": ["Req 6.5.1"]}


def test_map_compliance_single_cwe_multiple_standards():
    result = map_compliance(["CWE-89"])
    assert "PCI-DSS" in result
    assert "SOC2" in result
    assert "ISO27001" in result
    assert result["PCI-DSS"] == ["Req 6.5.1"]
    assert result["SOC2"] == ["CC6.1"]
    assert result["ISO27001"] == ["A.14.2.5"]


def test_map_compliance_multiple_cwes():
    result = map_compliance(["CWE-89", "CWE-79"], standards=["PCI-DSS"])
    # both CWEs map to same standard -> union of controls, sorted
    assert result == {"PCI-DSS": ["Req 6.5.1", "Req 6.5.7"]}


def test_map_compliance_filter_standards():
    result = map_compliance(["CWE-89"], standards=["PCI-DSS", "GDPR"])
    # GDPR has no mapping for CWE-89 -> only PCI in result
    assert "PCI-DSS" in result
    assert "GDPR" not in result


def test_map_compliance_empty_cwe_ids():
    result = map_compliance([])
    assert result == {}


def test_map_compliance_unknown_cwe():
    result = map_compliance(["CWE-9999"])
    assert result == {}


def test_map_compliance_no_duplicates():
    # CWE-89 appears twice in input -> controls not duplicated
    result = map_compliance(["CWE-89", "CWE-89"], standards=["PCI-DSS"])
    assert result == {"PCI-DSS": ["Req 6.5.1"]}


# --- enrich_compliance ---

def test_enrich_compliance_backward_compat():
    flags = ["PCI-DSS", "GDPR"]
    result = enrich_compliance(["CWE-89"], flags)
    # old field preserved
    assert result["compliance_flags"] == flags


def test_enrich_compliance_new_fields():
    flags = ["PCI-DSS"]
    result = enrich_compliance(["CWE-89"], flags)
    assert "compliance_controls" in result
    assert "compliance_standards" in result
    assert result["compliance_controls"]["PCI-DSS"] == ["Req 6.5.1"]
    assert "PCI-DSS" in result["compliance_standards"]


def test_enrich_compliance_empty():
    result = enrich_compliance([], [])
    assert result["compliance_flags"] == []
    assert result["compliance_controls"] == {}
    assert result["compliance_standards"] == []


def test_enrich_compliance_sorted_standards():
    result = enrich_compliance(["CWE-89", "CWE-311"], [])
    # standards should be sorted alphabetically
    assert result["compliance_standards"] == sorted(result["compliance_standards"])


def test_enrich_compliance_does_not_mutate_input():
    flags = ["PCI-DSS"]
    flags_copy = list(flags)
    cwes = ["CWE-89"]
    cwes_copy = list(cwes)
    enrich_compliance(cwes, flags)
    assert flags == flags_copy
    assert cwes == cwes_copy


# --- COMPLIANCE_MAP data ---

def test_compliance_map_has_expected_standards():
    expected = {"PCI-DSS", "GDPR", "SOC2", "ISO27001", "HIPAA"}
    assert expected.issubset(set(COMPLIANCE_MAP.keys()))


def test_compliance_map_cwe_89_pci():
    assert COMPLIANCE_MAP["PCI-DSS"]["CWE-89"] == ["Req 6.5.1"]


def test_map_compliance_mixed_known_unknown():
    result = map_compliance(["CWE-89", "CWE-9999"], standards=["PCI-DSS"])
    assert result == {"PCI-DSS": ["Req 6.5.1"]}
