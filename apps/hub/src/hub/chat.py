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

from . import meter

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5-5"
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
            turns.append({"role": role, "content": text[:4000]})
    return turns


def reply(message: str, messages: list, api_key: str, model: str = "") -> dict:
    """Answer one client message. Returns ``{"text": ..., "model": ..., "ok": ...}``."""
    text = (message or "").strip()
    if not text:
        return {"ok": False, "error": "empty message", "text": ""}

    key = (api_key or os.getenv("VISHAP_HUB_LLM_KEY") or "").strip()
    if not key:
        return {"ok": True, "model": "local", "text": FALLBACK, "key_required": True}

    payload = {
        "model": (model or os.getenv("VISHAP_HUB_LLM_MODEL") or DEFAULT_MODEL).strip(),
        # Measured 2026-10-29: the worst full answer took 1298 output tokens, and thinking
        # is about 60% of what is spent. 1200 cut one long answer in three; 2400 leaves room.
        "max_tokens": 2400,
        "system": _prompt(),
        "messages": [*_history(messages), {"role": "user", "content": text[:4000]}],
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        ANTHROPIC_URL,
        data=body,
        method="POST",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        return {"ok": False, "text": "", "error": f"model refused: HTTP {exc.code} {detail}"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "text": "", "error": f"{type(exc).__name__}: {exc}"}

    meter.record(data.get("usage"))                 # paid for, whatever the answer turns out to be
    blocks = data.get("content") or []
    parts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
    answer = "\n".join(part for part in parts if part).strip()
    if data.get("stop_reason") == "max_tokens":
        # Cut by the limit. Text that came out is still worth showing, but it is marked
        # "truncated" so the client cannot mistake it for a whole answer. No text at all
        # (the budget went to thinking) is not an answer and stays a failure.
        if answer:
            return {"ok": True, "truncated": True, "text": answer, "error": ""}
        return {"ok": False, "text": "", "error": "answer truncated by the token limit"}
    if not answer:
        return {"ok": False, "text": "", "error": "the model returned no text"}
    return {"ok": True, "model": payload["model"], "text": answer}
