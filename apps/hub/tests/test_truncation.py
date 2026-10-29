"""A truncated answer says so.

With thinking on by default the whole token budget can go before any text appears, and
the model's answer is then cut mid-way. Before this, `proposal.py` reported that as "the
model did not return JSON" and `chat.py` handed back half a sentence as a success. Both
sent the reader to fix the wrong thing.
"""
import json

from hub import chat, proposal


class FakeResponse:
    """Enough of an http.client response for one JSON body."""

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self, *args):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def api(stop_reason: str, text: str | None) -> dict:
    content = [{"type": "text", "text": text}] if text is not None else [{"type": "thinking", "thinking": "..."}]
    return {"content": content, "stop_reason": stop_reason}


# proposal ---------------------------------------------------------------------

def test_a_proposal_cut_by_the_limit_is_not_a_json_problem(monkeypatch):
    monkeypatch.setattr(proposal.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(api("max_tokens", '{"verdict": "SA')))
    result = proposal._call("k", "m", "material", "", "")
    assert result["ok"] is False
    assert result["error"] == "answer truncated by the token limit"


def test_an_empty_thinking_only_answer_still_says_json(monkeypatch):
    monkeypatch.setattr(proposal.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(api("end_turn", None)))
    result = proposal._call("k", "m", "material", "", "")
    assert result["ok"] is False
    assert result["error"] == "the model did not return JSON"


def test_a_complete_proposal_still_parses(monkeypatch):
    body = json.dumps({"verdict": "SAFE", "summary": "fine", "findings": [], "patch": {}})
    monkeypatch.setattr(proposal.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(api("end_turn", body)))
    result = proposal._call("k", "m", "material", "", "")
    assert result["ok"] is True
    assert result["parsed"]["verdict"] == "SAFE"


def test_propose_reports_the_truncation_to_its_caller(monkeypatch):
    monkeypatch.setenv("VISHAP_HUB_LLM_KEY", "k")
    monkeypatch.setattr(proposal.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(api("max_tokens", '{"verdict"')))
    result = proposal.propose(material="x = 1")
    assert result["ok"] is False
    assert "truncated" in result["error"]


# chat -------------------------------------------------------------------------

def test_a_chat_answer_cut_by_the_limit_keeps_its_text_and_says_truncated(monkeypatch):
    monkeypatch.setattr(chat.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(api("max_tokens", "Half a sentence that")))
    result = chat.reply("hello", [], "k")
    assert result["ok"] is True
    assert result["truncated"] is True
    assert result["text"] == "Half a sentence that"
    assert result["error"] == ""


def test_a_chat_answer_cut_before_any_text_is_not_ok(monkeypatch):
    monkeypatch.setattr(chat.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(api("max_tokens", None)))
    result = chat.reply("hello", [], "k")
    assert result["ok"] is False
    assert result["text"] == ""
    assert result["error"] == "answer truncated by the token limit"


def test_a_complete_chat_answer_is_still_ok(monkeypatch):
    monkeypatch.setattr(chat.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(api("end_turn", "All of it.")))
    result = chat.reply("hello", [], "k")
    assert result["ok"] is True
    assert result["text"] == "All of it."


def test_an_empty_chat_answer_keeps_its_old_message(monkeypatch):
    monkeypatch.setattr(chat.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(api("end_turn", "")))
    result = chat.reply("hello", [], "k")
    assert result["ok"] is False
    assert result["error"] == "the model returned no text"


def test_the_fallback_no_longer_promises_three_services():
    assert "three services" not in chat.FALLBACK
    assert "generator" in chat.FALLBACK and "validator" in chat.FALLBACK
