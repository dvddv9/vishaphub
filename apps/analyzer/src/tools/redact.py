# -*- coding: utf-8 -*-
"""Pre-LLM PII/secrets redaction.

Dogfood finding (P0): PII and secrets were sent to the cloud LLM
before being detected. Detection ran only in run_audit() AFTER all
stages. This module redacts PII/secrets BEFORE any LLM call.

Uses the same regex patterns as orchestrator.PII_PATTERNS to keep
detection and redaction in sync.
"""
import re

from src.tools.patterns import PII_PATTERNS


# Placeholder per PII category
PLACEHOLDERS = {
    "email": "<EMAIL_REDACTED>",
    "phone_ru": "<PHONE_REDACTED>",
    "passport_ru": "<PASSPORT_REDACTED>",
    "snils": "<SNILS_REDACTED>",
    "iban": "<IBAN_REDACTED>",
    "aws_access_key": "<AWS_ACCESS_KEY_REDACTED>",
    "aws_secret_key": "<AWS_SECRET_KEY_REDACTED>",
    "stripe_live_key": "<STRIPE_LIVE_KEY_REDACTED>",
    "stripe_test_key": "<STRIPE_TEST_KEY_REDACTED>",
    "github_token": "<GITHUB_TOKEN_REDACTED>",
    "slack_token": "<SLACK_TOKEN_REDACTED>",
    "google_api_key": "<GOOGLE_API_KEY_REDACTED>",
    "private_key": "<PRIVATE_KEY_REDACTED>",
    "hardcoded_password": "<PASSWORD_REDACTED>",
    "hardcoded_secret": "<SECRET_REDACTED>",
}


_VALUE_ONLY = ("hardcoded_password", "hardcoded_secret")


#: Card numbers are deliberately not in PII_PATTERNS: a regex alone cannot tell a PAN from an
#: order number, and a wide pattern would redact every long figure in the material. Luhn can:
#: the candidate has 13-19 digits and its checksum holds, which order numbers rarely satisfy.
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = ord(char) - 48
        if position % 2:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _redact_cards(text: str) -> tuple[str, int]:
    """Replace card numbers with a placeholder; a candidate that fails Luhn is left alone."""
    found = {"n": 0}

    def swap(match: "re.Match[str]") -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if not 13 <= len(digits) <= 19 or not _luhn_ok(digits):
            return match.group(0)
        found["n"] += 1
        return "<CARD_REDACTED>"

    return _CARD.sub(swap, text), found["n"]


def _hide_value(match_text: str, placeholder: str) -> str:
    """`name = "value"` -> `name = "<PLACEHOLDER>"` (the quotes and the name stay)."""
    quotes = [i for i in (match_text.find('"'), match_text.find("'")) if i >= 0]
    if not quotes:
        return placeholder
    i = min(quotes)
    return match_text[:i + 1] + placeholder + match_text[-1]


def redact_pii(text: str) -> tuple[str, dict]:
    """Replace PII/secrets with placeholders.

    Args:
        text: material text (may contain PII/secrets)

    Returns:
        (redacted_text, mapping) where mapping = {category: count}

    Note: this function is idempotent — running it twice is safe.
    """
    if not text:
        return text, {}

    redacted = text
    mapping = {}

    for name, pattern in PII_PATTERNS.items():
        placeholder = PLACEHOLDERS.get(name, "<{}_REDACTED>".format(name.upper()))
        matches = pattern.findall(redacted)
        if matches:
            mapping[name] = len(matches)
            if name in _VALUE_ONLY:
                # keep `API_KEY = "` ... `"`: the model must still see that the variable exists and is
                # used, otherwise it reports "API_KEY is undefined" (NameError) for a defined constant.
                redacted = pattern.sub(lambda m, ph=placeholder: _hide_value(m.group(0), ph), redacted)
            else:
                redacted = pattern.sub(placeholder, redacted)

    redacted, cards = _redact_cards(redacted)
    if cards:
        mapping["card_pan"] = cards

    return redacted, mapping


def is_redacted(text: str) -> bool:
    """Check if text contains any redaction placeholders."""
    return "<" in text and "_REDACTED>" in text
