"""Keep an API key out of anything that is shown or logged."""

from __future__ import annotations


def short(body: bytes, key: str) -> str:
    """The first 500 bytes of an endpoint's answer, with the key replaced."""
    text = body[:500].decode("utf-8", errors="replace")
    return text.replace(key, "[key]") if key else text
