"""One set of values goes through every route that can reach a model, a log, a report or an error.

A card number with a valid checksum is redacted wherever the client typed it. A long figure that is
not a card (an order number, an epoch in milliseconds, a random sequence) is left alone: a wide
pattern would redact every long figure in the material and make the answer useless.
"""
import hashlib
import io
import json
import logging
import urllib.error
import urllib.request

import pytest

from hub import chat, pipeline, privacy, proposal
from hub.router import plan_for

CARD = "4111 1111 1111 1111"        # Luhn-valid test number
CARD_DASHED = "5500-0000-0000-0004"  # Luhn-valid test number, other separator
ORDER = "1793087996386"             # 13 digits, an epoch in milliseconds
RANDOM_LONG = "1234567890123456"    # 16 digits, fails Luhn


def _luhn(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if flip:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        total += n
        flip = not flip
    return total % 10 == 0


def test_the_fixtures_are_what_they_claim_to_be():
    assert _luhn(CARD.replace(" ", "")) and _luhn(CARD_DASHED.replace("-", ""))
    assert not _luhn(ORDER) and not _luhn(RANDOM_LONG)


@pytest.fixture()
def wire(monkeypatch):
    """Everything the hub would send to a provider, captured; nothing really goes out."""
    sent: list[str] = []

    def fake_open(request, timeout=0):
        sent.append(request.data.decode("utf-8"))
        raise urllib.error.URLError("stop")

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    return sent


def _body(sent):
    assert sent, "nothing was sent"
    return sent[-1]


ROUTES = {
    "proposal.material": lambda text: proposal._call("k", "m", text, "", ""),
    "proposal.spec": lambda text: proposal._call("k", "m", "x = 1", text, ""),
    "proposal.question": lambda text: proposal._call("k", "m", "x = 1", "", text),
    "chat.message": lambda text: chat.reply(text, [], "k"),
    "chat.history": lambda text: chat.reply("hello", [{"role": "user", "content": text}], "k"),
}


@pytest.mark.parametrize("route", ROUTES)
def test_a_valid_card_never_reaches_the_provider(wire, route):
    ROUTES[route](f"charge {CARD} and also {CARD_DASHED} now")
    body = _body(wire)
    assert "4111" not in body and "5500" not in body


@pytest.mark.parametrize("route", ROUTES)
def test_a_number_that_is_not_a_card_is_left_alone(wire, route):
    ROUTES[route](f"order {ORDER} trace {RANDOM_LONG}")
    body = _body(wire)
    assert ORDER in body and RANDOM_LONG in body


@pytest.mark.parametrize("route", ROUTES)
def test_without_redaction_nothing_is_sent(wire, monkeypatch, route):
    def down(text):
        raise privacy.RedactionUnavailable(privacy.REFUSAL)

    monkeypatch.setattr(privacy, "redact_text", down)
    result = ROUTES[route](f"charge {CARD}")
    assert result["ok"] is False and result["error"] == privacy.REFUSAL
    assert wire == []


@pytest.mark.parametrize("module,call", [
    (proposal, lambda: proposal._call("k", "m", "x = 1", "", "")),
    (chat, lambda: chat.reply("hello", [], "k")),
])
def test_a_provider_error_that_echoes_the_input_is_scrubbed(monkeypatch, module, call):
    def refuse(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 400, "bad request", {},
                                     io.BytesIO(f'{{"error":"invalid input {CARD}"}}'.encode()))

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    result = call()
    assert result["ok"] is False
    assert "4111" not in result["error"] and "HTTP 400" in result["error"]


def test_the_run_report_the_fingerprint_and_the_logs_do_not_hold_the_card(caplog):
    material = f'logger.info("charge card {CARD} order {ORDER}")\n'
    with caplog.at_level(logging.DEBUG):
        result = pipeline.run_plan(plan_for("analyse"), material=material)
    blob = json.dumps(result.__dict__, default=lambda o: getattr(o, "__dict__", str(o)), ensure_ascii=False)
    assert "4111" not in blob and "4111" not in caplog.text


def test_redaction_does_not_change_what_the_fingerprint_says_about_the_input():
    """The fingerprint names the material the client sent, not the redacted text the model saw."""
    material = f"charge {CARD}\nx = 1\n"
    first = pipeline.run_plan(plan_for("analyse"), material=material)
    again = pipeline.run_plan(plan_for("analyse"), material=material)
    assert first.fingerprint["body"]["material_sha256"] == hashlib.sha256(material.encode()).hexdigest()
    assert first.fingerprint["id"] == again.fingerprint["id"]
    other = pipeline.run_plan(plan_for("analyse"), material=material.replace(CARD, "4111 1111 1111 1112"))
    assert other.fingerprint["id"] != first.fingerprint["id"]