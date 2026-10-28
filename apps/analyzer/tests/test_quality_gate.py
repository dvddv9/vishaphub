# -*- coding: utf-8 -*-
"""Tests for Quality Gates (P1-5)."""

from src.tools.quality_gate import (
    load_quality_gate,
    evaluate_gate,
    normalize_priority,
    DEFAULT_CONFIG,
)


def _rn(priority="критично", name="x", cwe=None, file=None):
    d = {"id": "RN-1", "name": name, "priority": priority, "note": "n"}
    if cwe:
        d["cwe"] = cwe
    if file:
        d["file"] = file
    return d


def test_normalize_priority_ru_en():
    assert normalize_priority("критично") == "critical"
    assert normalize_priority("важно") == "high"
    assert normalize_priority("опционально") == "medium"
    assert normalize_priority("critical") == "critical"
    assert normalize_priority("HIGH") == "high"
    assert normalize_priority("") == "low"
    assert normalize_priority("unknown") == "low"


def test_load_missing_file_returns_default(tmp_path):
    cfg = load_quality_gate(str(tmp_path / "nope.yml"))
    assert cfg["fail_on"] == DEFAULT_CONFIG["fail_on"]
    assert cfg["max_critical"] == 0


def test_load_valid_yaml(tmp_path):
    p = tmp_path / ".vishap.yml"
    p.write_text(
        "quality_gate:\n"
        "  max_critical: 2\n"
        "  max_high: 5\n"
        "  fail_on: [critical]\n",
        encoding="utf-8",
    )
    cfg = load_quality_gate(str(p))
    assert cfg["max_critical"] == 2
    assert cfg["max_high"] == 5


def test_load_invalid_yaml_returns_default(tmp_path):
    p = tmp_path / ".vishap.yml"
    p.write_text("not: [valid: yaml", encoding="utf-8")
    cfg = load_quality_gate(str(p))
    assert cfg["max_critical"] == DEFAULT_CONFIG["max_critical"]


def test_evaluate_empty_findings():
    result = evaluate_gate([], DEFAULT_CONFIG)
    assert result["passed"] is True
    assert result["total"] == 0


def test_evaluate_max_critical_ok():
    # max_critical=0; 0 critical -> pass
    result = evaluate_gate([_rn(priority="важно")], DEFAULT_CONFIG)
    assert result["passed"] is True


def test_evaluate_max_critical_fail():
    result = evaluate_gate([_rn(priority="критично")], DEFAULT_CONFIG)
    assert result["passed"] is False
    assert "critical" in result["reasons"][0]


def test_evaluate_max_high():
    cfg = dict(DEFAULT_CONFIG, max_high=2)
    result = evaluate_gate([_rn(priority="важно")] * 3, cfg)
    assert result["passed"] is False
    assert result["high"] == 3


def test_evaluate_ignore_low():
    cfg = dict(DEFAULT_CONFIG, ignore=["low", "info"])
    result = evaluate_gate([_rn(priority="")], cfg)
    assert result["passed"] is True
    assert result["ignored"] == 1


def test_evaluate_ignore_rules():
    cfg = dict(DEFAULT_CONFIG, ignore_rules=["CWE-79"])
    result = evaluate_gate([_rn(priority="критично", cwe="CWE-79")], cfg)
    assert result["passed"] is True
    assert result["ignored"] == 1


def test_evaluate_ignore_paths():
    cfg = dict(DEFAULT_CONFIG, ignore_paths=["tests/"])
    result = evaluate_gate(
        [_rn(priority="критично", file="tests/test_x.py")],
        cfg,
    )
    assert result["passed"] is True


def test_evaluate_fail_on_reachable():
    cfg = dict(DEFAULT_CONFIG, fail_on_reachable=True)
    result = evaluate_gate([], cfg, reachable=True)
    assert result["passed"] is False
    assert "reachable" in result["reasons"][0]


def test_evaluate_fail_on_reachable_not_triggered():
    cfg = dict(DEFAULT_CONFIG, fail_on_reachable=True)
    result = evaluate_gate([], cfg, reachable=False)
    assert result["passed"] is True


def test_evaluate_non_dict_findings_ignored():
    result = evaluate_gate([None, "x", 123], DEFAULT_CONFIG)
    assert result["passed"] is True
    assert result["total"] == 0


def test_evaluate_invalid_config_falls_back():
    result = evaluate_gate([_rn(priority="критично")], "not a dict")
    assert result["passed"] is False
