# -*- coding: utf-8 -*-
"""v7.4.7 P0: #3 log blast by content, #4 stable material_hash, #6 SEC regex negation."""
import pytest

from src.pipeline.orchestrator import compute_hash
from src.pipeline.verdict import _has_critical_sec_in_text
from src.tools.patterns import detect_exploitability

CLEAN_LOG = (
    "2026-10-27 18:00:02 INFO server listening on 0.0.0.0:5432\n"
    "2026-10-27 18:00:03 INFO request id=1793087996386 GET /health 200 12ms\n"
    "2026-10-27 18:00:04 INFO SELECT count(*) FROM users took 3ms\n"
)


# ---- #3
def test_clean_log_blast_none():
    r = detect_exploitability(CLEAN_LOG)
    assert r["blast_radius"] == "none"
    assert r["reachable"] is False


def test_one_line_log_blast_none():
    assert detect_exploitability("2026-10-27 18:00:00")["blast_radius"] == "none"


@pytest.mark.parametrize("line", [
    "JWT_SECRET=abc123",
    "user alice@example.com logged in",
    "q=1' OR '1'='1",
    "card 4111 1111 1111 1111",       # Luhn-valid test number
    "GET http://169.254.169.254/latest/meta-data",
])
def test_log_with_content_blast_high(line):
    r = detect_exploitability("2026-10-27 18:00:00 INFO " + line + "\n")
    assert r["blast_radius"] == "high"
    assert r["reachable"] is True
    assert r["blast_indicators"]


def test_log_config_only_blast_medium():
    r = detect_exploitability("2026-10-27 18:00:00 INFO Access-Control-Allow-Origin: *\n")
    assert r["blast_radius"] == "medium"


# ---- #4
def test_material_hash_is_stable_and_context_free():
    m = "def f():\n    return 1\n"
    assert compute_hash(m) == compute_hash(m)
    assert compute_hash(m) != compute_hash(m, context="a.py:sess-1-aaaa")


# ---- #6
@pytest.mark.parametrize("text", [
    "SEC-0003 (низкий) reviewed",
    "SEC-0003 (низкий): injection не нужен",
    "SEC-0003 low, no crash observed",
    "SEC-0004 crash not observed on fuzzing",
])
def test_sec_noncritical_not_flagged(text):
    assert _has_critical_sec_in_text(text) is False


@pytest.mark.parametrize("text", [
    "SEC-0001 критично",
    "Критично: SEC-0001",
    "SEC-0002 critical: SQL injection in /login",
    "SEC-0003 (низкий) ok\nSEC-0001 критично: overflow",
    "SEC-0005 CVE-2024-1234 in dependency",
])
def test_sec_critical_still_flagged(text):
    assert _has_critical_sec_in_text(text) is True
