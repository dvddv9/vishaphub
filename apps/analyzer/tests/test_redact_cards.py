# -*- coding: utf-8 -*-
"""Card numbers are redacted by checksum, not by shape.

A regex on digit runs would either miss card numbers with spaces or eat every long figure in
the material. Luhn is the cheapest thing that tells a PAN from an order number, so the test
holds both halves: the valid card goes, the invalid one stays.
"""
from src.tools.redact import redact_pii


def test_a_luhn_valid_card_is_redacted():
    clean, report = redact_pii("card 4111 1111 1111 1111 on file")
    assert "4111" not in clean
    assert "<CARD_REDACTED>" in clean
    assert report["card_pan"] == 1


def test_a_card_without_spaces_is_redacted_too():
    clean, report = redact_pii("pan=4111111111111111")
    assert clean == "pan=<CARD_REDACTED>"
    assert report["card_pan"] == 1


def test_a_number_that_fails_luhn_is_left_alone():
    text = "order 1234 5678 9012 3456 shipped"
    clean, report = redact_pii(text)
    assert clean == text
    assert "card_pan" not in report


def test_a_short_number_is_not_a_card():
    text = "build 1234567890123 done"
    clean, report = redact_pii(text)
    assert clean == text
    assert "card_pan" not in report


def test_card_and_email_together_are_both_reported():
    clean, report = redact_pii("4111111111111111 for ivan.petrov@example.com")
    assert clean == "<CARD_REDACTED> for <EMAIL_REDACTED>"
    assert report == {"email": 1, "card_pan": 1}
