# -*- coding: utf-8 -*-
"""Offline checks on matched secrets (src/tools/secret_check.py) and how static_scan uses them."""
from src.tools.secret_check import assess, github_checksum_ok, github_token_with_checksum, is_placeholder
from src.tools.secret_check import live_check_enabled, validate_live
from src.tools.static_scan import scan_material, verdict_of

ENTROPY = "abcdefghijklmnopqrstuvwxyz0123"          # 30 characters
GOOD = "ghp_" + github_token_with_checksum(ENTROPY)
BAD = GOOD[:-1] + ("A" if GOOD[-1] != "A" else "B")


def _by_id(result, rid):
    return [f for f in result["findings"] if f["id"] == rid]


def test_checksum_round_trip_and_mismatch():
    assert github_checksum_ok(GOOD) is True
    assert github_checksum_ok(BAD) is False
    assert github_checksum_ok("ghp_short") is None


def test_placeholder_words_and_repeats():
    assert is_placeholder("sk_" + "live_EXAMPLEEXAMPLEEXAMPLE")
    assert is_placeholder("changeme_please")
    assert is_placeholder("A" * 12)
    assert not is_placeholder("Zk3Qm9Xv1Rt7Lp2Hn5Bc8Dw4")


def test_aws_key_alphabet():
    assert assess("secret-aws", "AKIA" + "ABCDEFGH23456723")["confidence"] == "high"
    assert assess("secret-aws", "AKIA" + "ABCDEFGH01890189")["confidence"] == "low"


def test_checksum_mismatch_annotates_and_keeps_severity():
    r = scan_material(f'TOKEN = "{BAD}"\n', "app.py")
    (f,) = _by_id(r, "secret-token")
    assert f["severity"] == "critical"            # a failed structural check never lowers severity
    assert f["confidence"] == "low" and "verify" in f["note"]


def test_valid_token_is_high_confidence():
    r = scan_material(f'TOKEN = "{GOOD}"\n', "app.py")
    (f,) = _by_id(r, "secret-token")
    assert f["severity"] == "critical" and f["confidence"] == "high"


def test_placeholder_goes_to_low_but_stays_listed_and_blocks_safe():
    r = scan_material('password = "changeme_please"\n', "app.py")
    (f,) = _by_id(r, "secret-hardcoded")
    assert f["severity"] == "low" and f["confidence"] == "low"
    assert verdict_of(r) != "SAFE"


def test_named_secret_rule_also_checks_placeholder_value():
    r = scan_material('PAYMENT_API_KEY = "placeholder_value_123"\n', "app.py")
    (f,) = _by_id(r, "secret-hardcoded-named")
    assert f["severity"] == "low" and f["confidence"] == "low"


def test_real_looking_password_unchanged():
    password = "Zk3Qm9" + "Xv1Rt7"
    r = scan_material(f'password = "{password}"\n', "app.py")
    (f,) = _by_id(r, "secret-hardcoded")
    assert f["severity"] == "high" and "confidence" not in f


def test_snippet_still_masks_the_value():
    r = scan_material(f'TOKEN = "{GOOD}"\n', "app.py")
    assert GOOD not in r["findings"][0]["snippet"]


def test_live_check_is_opt_in_and_reports_provider_result_without_token(monkeypatch):
    monkeypatch.delenv("VISHAP_SECRET_LIVE_CHECK", raising=False)
    assert live_check_enabled() is False
    assert validate_live("secret-token", GOOD, request_fn=lambda *_: (_ for _ in ()).throw(AssertionError())) is None

    monkeypatch.setenv("VISHAP_SECRET_LIVE_CHECK", "1")
    calls = []

    def request(url, token, provider):
        calls.append((url, token, provider))
        return 200, {"login": "test-account"}

    result = validate_live("secret-token", GOOD, request_fn=request)
    assert result == {"provider": "github", "status": "active"}
    finding = assess("secret-token", GOOD, result)
    assert finding["credential_status"] == "active"
    assert GOOD not in repr(finding)
    assert calls == [("https://api.github.com/user", GOOD, "github")]


def test_live_check_does_not_call_403_inactive(monkeypatch):
    monkeypatch.setenv("VISHAP_SECRET_LIVE_CHECK", "true")
    result = validate_live("secret-token", GOOD, request_fn=lambda *_: (403, {}))
    assert result["status"] == "unknown"
