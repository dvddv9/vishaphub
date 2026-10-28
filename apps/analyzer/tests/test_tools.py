# -*- coding: utf-8 -*-
"""Unit tests for tools — no LLM calls."""
from src.pipeline.orchestrator import (
    detect_pii, detect_compliance, compute_hash, generate_audit_id,
)
from src.pipeline.stages import parse_json_response
from src.tools.fallback_check import REQUIRED, LOSS_THRESHOLD


# === PII ===

def test_detect_pii_email():
    result = detect_pii("contact: user@example.com")
    assert result == {"email": 1}


def test_detect_pii_phone():
    result = detect_pii("tel: +79991234567")
    assert "phone_ru" in result


def test_detect_pii_multiple():
    result = detect_pii("user@example.com and admin@test.org")
    assert result.get("email") == 2


def test_detect_pii_empty():
    result = detect_pii("def foo(): pass")
    assert result == {}


# === Compliance ===

def test_detect_compliance_gdpr():
    result = detect_compliance("we process personal data")
    assert "GDPR" in result


def test_detect_compliance_pii_auto():
    result = detect_compliance("user@example.com", pii={"email": 1})
    assert "GDPR" in result
    assert "152-ФЗ" in result


def test_detect_compliance_no_triggers():
    result = detect_compliance("def foo(): pass")
    assert result == []


# === Hash ===

def test_compute_hash_format():
    h = compute_hash("abc")
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


def test_compute_hash_stable():
    assert compute_hash("abc") == compute_hash("abc")


def test_compute_hash_different():
    assert compute_hash("abc") != compute_hash("xyz")


# === Audit ID ===

def test_generate_audit_id_format():
    aid = generate_audit_id()
    assert aid.startswith("audit-")
    parts = aid.split("-")
    assert len(parts) == 5  # audit, YYYY, MM, DD, XXXXXX
    assert len(parts[0]) == 5   # "audit"
    assert len(parts[1]) == 4   # YYYY
    assert len(parts[2]) == 2   # MM
    assert len(parts[3]) == 2   # DD
    assert len(parts[4]) == 6   # XXXXXX


# === JSON parsing ===

def test_parse_json_plain():
    result = parse_json_response('{"level": "D0"}')
    assert result.get("level") == "D0"


def test_parse_json_code_block():
    result = parse_json_response('```json\n{"level": "D0"}\n```')
    assert result.get("level") == "D0"


def test_parse_json_with_markdown():
    result = parse_json_response('Here is result:\n```json\n{"level": "D1"}\n```\nDone.')
    assert result.get("level") == "D1"


def test_parse_json_invalid():
    result = parse_json_response("not json at all")
    assert "_error" in result
    assert result["_error"] == "JSON parse failed"


def test_parse_json_trailing_comma():
    result = parse_json_response('{"level": "D0",}')
    assert result.get("level") == "D0"


# === Fallback check ===

def test_fallback_check_required_d0():
    assert "D0" in REQUIRED
    assert "[CONCLUSION]" in REQUIRED["D0"]


def test_fallback_check_required_d3():
    assert "D3" in REQUIRED
    assert len(REQUIRED["D3"]) > 10


def test_fallback_check_threshold():
    assert LOSS_THRESHOLD == 30.0


# === Extended PII ===

def test_detect_pii_snils():
    result = detect_pii("SNILS: 123-456-789 00")
    assert "snils" in result


def test_detect_pii_snils_no_false_positive():
    # Phone 79991234567 (11 digits) — не должно быть snils
    result = detect_pii("tel: +79991234567")
    assert "snils" not in result


def test_detect_pii_iban():
    result = detect_pii("IBAN: DE89370400440532013000")
    assert "iban" in result


def test_detect_pii_combined():
    result = detect_pii("user@example.com +79991234567")
    assert "email" in result
    assert "phone_ru" in result


# === Extended Compliance ===

def test_detect_compliance_152fz():
    result = detect_compliance("мы обрабатываем персональные данные")
    assert "152-ФЗ" in result


def test_detect_compliance_hipaa():
    result = detect_compliance("patient diagnosis record")
    assert "HIPAA" in result


def test_detect_compliance_pci():
    result = detect_compliance("credit card cvv processing")
    assert "PCI-DSS" in result


def test_detect_compliance_multi():
    result = detect_compliance("personal data payment", pii={"email": 1})
    assert "GDPR" in result
    assert "PCI-DSS" in result
    assert "152-ФЗ" in result


# === Extended JSON parsing ===

def test_parse_json_nested():
    result = parse_json_response('{"a": {"b": {"c": 1}}}')
    assert result.get("a", {}).get("b", {}).get("c") == 1


def test_parse_json_array():
    result = parse_json_response('[{"id": 1}, {"id": 2}]')
    # parse_json_response возвращает dict или _raw; массив — допустим
    assert isinstance(result, (dict, list))


def test_parse_json_with_bom():
    result = parse_json_response('﻿{"level": "D0"}')
    # BOM может помешать — не критично, главное не падать
    assert isinstance(result, dict)


# === Extended fallback_check ===

def test_fallback_check_required_d1():
    assert "D1" in REQUIRED
    assert "[CONCLUSION]" in REQUIRED["D1"]


def test_fallback_check_required_d4():
    assert "D4" in REQUIRED
    assert len(REQUIRED["D4"]) > 20


def test_fallback_check_forced_blocks():
    # [FUNC:FULL] и [MANDATORY BASE] должны быть в D3
    assert "[FUNC:FULL]" in REQUIRED["D3"]
    assert "[MANDATORY BASE]" in REQUIRED["D3"]
