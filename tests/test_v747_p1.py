# -*- coding: utf-8 -*-
"""v7.4.7 P1: #1 Luhn in scan_log, #2 sqli / cmd_injection / pii_phone coverage without noise."""
import pytest

from src.tools.sast import LOG_PATTERNS, luhn_ok, scan_log
from src.tools.patterns import detect_exploitability

PFX = "2026-10-27 18:00:00 INFO "


def _types(line):
    return {f["type"] for f in scan_log(PFX + line + "\n")}


CLEAN_LOG = (
    "2026-10-27 18:00:02 INFO server listening on 0.0.0.0:5432\n"
    "2026-10-27 18:00:03 INFO connected db host=10.0.0.5 port=5432\n"
    "2026-10-27 18:00:04 INFO request id=1793087996386 took 12ms pid=18234\n"
    "2026-10-27 18:00:05 INFO SELECT count(*) FROM users took 3ms\n"
    "2026-10-27 18:00:06 INFO system health ok, call system update done\n"
)


def test_clean_log_no_findings():
    assert scan_log(CLEAN_LOG) == []
    assert detect_exploitability(CLEAN_LOG)["blast_radius"] == "none"


# ---- #1
def test_luhn():
    assert luhn_ok("4111 1111 1111 1111")
    assert not luhn_ok("1793087996386")
    assert not luhn_ok("123")


def test_credit_card_epoch_id_not_flagged():
    assert "credit_card" not in _types("request id=1793087996386")


def test_credit_card_real_number_flagged():
    assert "credit_card" in _types("card 4111 1111 1111 1111")


# ---- #2
@pytest.mark.parametrize("line", [
    "q=1' OR '1'='1",
    "q=1 UNION SELECT password FROM users--",
    "id=1' or 1=1--",
])
def test_sqli_flagged(line):
    assert "sqli_pattern" in _types(line)


@pytest.mark.parametrize("line", [
    "SELECT count(*) FROM users took 3ms",
    "SELECT id FROM orders WHERE id=5",
])
def test_sqli_plain_select_not_flagged(line):
    assert "sqli_pattern" not in _types(line)


@pytest.mark.parametrize("line", [
    "ping -c 1 8.8.8.8; cat /etc/passwd",
    "host=8.8.8.8|cat /etc/passwd",
    "x=1; cat /etc/passwd",
])
def test_cmd_injection_flagged(line):
    assert "cmd_injection" in _types(line)


@pytest.mark.parametrize("line", ["system health ok", "call system update", "cat readme.txt"])
def test_cmd_injection_plain_text_not_flagged(line):
    assert "cmd_injection" not in _types(line)


@pytest.mark.parametrize("line", [
    "phone +7 900 123 45 67",
    "phone +7 (900) 123-45-67",
    "phone 89001234567",
    "phone +1-555-123-4567",
    "phone +49-30-1234567",
])
def test_phone_flagged(line):
    assert "pii_phone" in _types(line)


@pytest.mark.parametrize("line", [
    "listening on 0.0.0.0:5432",
    "took 18:00:02",
    "request id=1793087996386",
    "pid=18234 uptime=00:00:02",
    "version 7.4.7 build 20261027",
])
def test_phone_noise_not_flagged(line):
    assert "pii_phone" not in _types(line)


def test_every_pattern_still_hits_its_sample():
    samples = {
        "db_password": "postgres://admin:hunter2@db:5432/x",
        "jwt_secret": "JWT_SECRET=abc123",
        "aws_key": "AKIAIOSFODNN7EXAMPLE",
        "aws_secret": "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI",
        "stripe_key": "sk_live_abcdef123456",
        "pii_email": "user alice@example.com logged in",
        "pii_phone": "phone +7-900-123-45-67",
        "pii_passport_ru": "Passport RU: 4510 123456",
        "credit_card": "card 4111 1111 1111 1111",
        "jwt_token": "eyJhbGciOi.eyJzdWIiOiIx.SflKxwRJSM",
        "ssh_key": "-----BEGIN RSA PRIVATE KEY-----",
        "sqlmap": "UA sqlmap/1.7",
        "sqli_pattern": "q=1' OR '1'='1",
        "cmd_injection": "ping -c 1 8.8.8.8; cat /etc/passwd",
        "imdsv1": "GET http://169.254.169.254/latest/meta-data",
        "cors_wildcard": "Access-Control-Allow-Origin: *",
        "csp_wildcard": "Content-Security-Policy: *",
        "cookie_insecure": "Set-Cookie sid=1; HttpOnly=false",
        "xff_trust": "X-Forwarded-For: 127.0.0.1",
    }
    assert set(samples) == set(LOG_PATTERNS)
    for name, line in samples.items():
        assert name in _types(line), name
