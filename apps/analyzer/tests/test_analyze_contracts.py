# -*- coding: utf-8 -*-
"""Tests for analyze.py --mode contracts (v6.1)."""
from src.tools.analyze import analyze_contracts


def test_detects_try_except():
    code = "def f():\n    try:\n        pass\n    except Exception:\n        pass\n"
    result = analyze_contracts(code)
    assert result["error_handling"] is True


def test_detects_retry_decorator():
    code = "from tenacity import retry\n\n@retry\ndef f():\n    pass\n"
    result = analyze_contracts(code)
    assert result["retry"] is True


def test_detects_timeout_param():
    code = "import requests\nrequests.get('http://x', timeout=30)\n"
    result = analyze_contracts(code)
    assert result["timeout"] is True


def test_detects_idempotency_key():
    code = "headers = {'idempotency_key': 'abc-123'}\n"
    result = analyze_contracts(code)
    assert result["idempotency"] is True


def test_clean_no_contracts():
    code = "def add(a, b):\n    return a + b\n"
    result = analyze_contracts(code)
    assert result["error_handling"] is False
    assert result["retry"] is False
    assert result["timeout"] is False
    assert result["idempotency"] is False
