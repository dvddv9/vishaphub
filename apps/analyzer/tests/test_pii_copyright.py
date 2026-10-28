# -*- coding: utf-8 -*-
"""Regression: PII must ignore emails in copyright/license headers.

Bug v5.8-v5.10.6: detect_pii flagged emails in Wireshark copyright header
(packet-btl2cap.c) as PII -> false positive GDPR/152-FZ.
Dogfood find 2026-10-14.
"""
from src.pipeline.orchestrator import detect_pii


WIRESHARK_HEADER = (
    "/*\n"
    " * Copyright 2002, Christoph Scholz <scholz@cs.uni-bonn.de>\n"
    " * By Gerald Combs <gerald@wireshark.org>\n"
    " */\n"
    "int main() { return 0; }\n"
)


def test_copyright_email_not_pii():
    """Copyright email -> not PII."""
    r = detect_pii(WIRESHARK_HEADER)
    assert "email" not in r, f"FAIL: copyright flagged, got {r}"


def test_license_email_not_pii():
    """License header email -> not PII."""
    text = "/* Licensed under GPL. Contact: gnu@gnu.org */"
    r = detect_pii(text)
    assert "email" not in r


def test_author_email_not_pii():
    """Author header email -> not PII."""
    text = "# Author: John Doe <john@example.com>"
    r = detect_pii(text)
    assert "email" not in r


def test_real_pii_email_still_detected():
    """Real PII email (not in copyright) -> detected."""
    text = 'user_email = "ivan@example.com"\nsend(user_email)'
    r = detect_pii(text)
    assert "email" in r, f"FAIL: real PII missed, got {r}"


def test_comment_pii_still_detected():
    """Email in comment (no copyright marker) -> detected."""
    text = "# contact: admin@company.com for support"
    r = detect_pii(text)
    assert "email" in r


def test_apache_license_email_not_pii():
    """Apache license email -> not PII."""
    text = "/* Copyright 2020 The Apache Software Foundation <dev@apache.org> */"
    r = detect_pii(text)
    assert "email" not in r
