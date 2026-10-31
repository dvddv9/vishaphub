"""What may leave the hub for a model, and what may be said about a failure.

One place decides it. Every text a client controls (material, spec, question, chat message and the
history of the chat) goes through `redact_text` before it is put in a request to a model provider, and
the text of a provider's error answer goes through `scrub_error` before it is returned or logged.

The redaction itself is the analyser's (`src.tools.redact`): secrets by pattern, card numbers by Luhn
checksum, so an order number or a long random figure stays as it was. If that code is not in the image
nothing is sent: a hub that cannot redact does not guess that the text is clean.
"""
from __future__ import annotations

REFUSAL = "redaction is unavailable; nothing was sent to the model"


class RedactionUnavailable(RuntimeError):
    """The analyser's redaction is not importable here."""


def redact_text(text: str) -> tuple[str, dict]:
    """The text with secrets and card numbers replaced, and what was replaced (counts by kind)."""
    try:
        from src.tools.redact import redact_pii
    except ImportError as exc:
        raise RedactionUnavailable(REFUSAL) from exc
    return redact_pii(text or "")


def merge_counts(*counts: dict) -> dict:
    total: dict = {}
    for one in counts:
        for kind, number in (one or {}).items():
            total[kind] = total.get(kind, 0) + number
    return total


def scrub_error(text: str, limit: int = 200) -> str:
    """A provider's error text, redacted and cut. Withheld entirely when it cannot be redacted."""
    try:
        clean, _ = redact_text(text)
    except RedactionUnavailable:
        return "(provider detail withheld)"
    return clean[:limit]