# -*- coding: utf-8 -*-
"""Keep API keys out of error text.

Providers sometimes echo (part of) the key in an error body, and exception text can
carry request details. Whatever reaches a report, a job record or a log goes through
``scrub`` first.
"""
from __future__ import annotations

import re

_KEY_LIKE = re.compile(
    r"(?i)\b(sk-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9]{8,}|xai-[A-Za-z0-9]{8,}|"
    r"AIza[0-9A-Za-z_-]{20,}|Bearer\s+[A-Za-z0-9._~+/=-]{12,})"
)


def scrub(text, *secrets: str | None) -> str:
    out = str(text)
    for sec in secrets:
        if sec and len(sec) >= 6:
            out = out.replace(sec, "[key hidden]")
    return _KEY_LIKE.sub("[key hidden]", out)
