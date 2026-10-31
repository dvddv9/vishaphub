"""The assistant: Vishap, speaking to the client.

Two rules shape this module:

* the model is the caller's — the hub holds no key of its own, so a conversation can
  never spend the owner's money silently;
* the assistant carries the process, it does not decide the verdict. It may route,
  ask, explain and refuse; the pipeline still answers for the run.

Without a key the assistant still answers — from a small local script that explains
what the hub does and where the key comes from. A page that says nothing is worse
than a page that says «bring a key».
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import llm, meter, privacy

DEFAULT_MODEL = llm.DEFAULT_ANTHROPIC_MODEL
MAX_TURNS = 12
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompt", "vishap.md")

FALLBACK = (
    "I am Vishap. One process does three jobs on the same material: the generator writes "
    "code from a spec, the validator checks it against that spec, the analyser checks "
    "whether it is dangerous — and I run them in order, returning the strictest verdict. "
    "I can route the request and explain the result, but the verdict is theirs, not mine. "
    "Without a model key I can only tell you this and point at console.anthropic.com for "
    "a key."
)

FALLBACK_NO_MODEL = (
    "I am Vishap. This installation runs without a language model: the rules and the validator "
    "check what you send, and the verdict is theirs. I can explain what the hub does, but I cannot "
    "read your code or answer free-form questions about it."
)


@dataclass
class Turn:
    role: str
    content: str


def _prompt() -> str:
    try:
        with open(PROMPT_PATH, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "You are Vishap, the assistant of VishapHub. Be short, concrete and honest."


def _history(messages: list) -> list[dict]:
    turns: list[dict] = []
    for item in messages[-MAX_TURNS:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        text = item.get("content")
        if role in ("user", "assistant") and isinstance(text, str) and text.strip():
            turns.append({"role": role, "content": text})
    return turns


def reply(message: str, messages: list, api_key: str, model: str = "", preset: str = "") -> dict:
    """Answer one client message. Returns ``{"text": ..., "model": ..., "ok": ...}``."""
    text = (message or "").strip()
    if not text:
        return {"ok": False, "error": "empty message", "text": ""}

    try:
        current = llm.settings(model, preset)
    except llm.ConfigError as exc:
        return {"ok": False, "text": "", "error": str(exc)}
    if current.provider == "none":
        return {"ok": True, "model": "local", "text": FALLBACK_NO_MODEL}
    key = llm.key_for(api_key, preset)
    if not key and current.key_required:
        return {"ok": True, "model": "local", "text": FALLBACK, "key_required": True}

    # The message and the history are the client's words: redacted like every other text that goes to
    # a model, and refused (nothing sent) when the redaction cannot run.
    try:
        text, redactions = privacy.redact_text(text)
        turns = []
        for turn in _history(messages):
            clean, found = privacy.redact_text(turn["content"])
            turns.append({"role": turn["role"], "content": clean[:4000]})
            redactions = privacy.merge_counts(redactions, found)
    except privacy.RedactionUnavailable:
        return {"ok": False, "text": "", "error": privacy.REFUSAL}
    # Measured 2026-10-29: the worst full answer took 1298 output tokens, and thinking
    # is about 60% of what is spent. 1200 cut one long answer in three; 2400 leaves room.
    url, headers, payload = llm.request_parts(
        current, key, _prompt(), [*turns, {"role": "user", "content": text[:4000]}], 2400)
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=llm.timeout(120)) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = privacy.scrub_error(exc.read().decode("utf-8", "replace"), 300)
        return {"ok": False, "text": "", "error": f"model refused: HTTP {exc.code} {detail}"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "text": "", "error": f"{type(exc).__name__}: {privacy.scrub_error(str(exc))}"}

    got = llm.read_reply(current, data)
    meter.record(got.usage)                         # paid for, whatever the answer turns out to be
    answer = got.text
    if got.truncated:
        # Cut by the limit. Text that came out is still worth showing, but it is marked
        # "truncated" so the client cannot mistake it for a whole answer. No text at all
        # (the budget went to thinking) is not an answer and stays a failure.
        if answer:
            return {"ok": True, "truncated": True, "text": answer, "error": ""}
        return {"ok": False, "text": "", "error": "answer truncated by the token limit"}
    if not answer:
        return {"ok": False, "text": "", "error": "the model returned no text"}
    return {"ok": True, "model": payload["model"], "text": answer}
