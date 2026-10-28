"""One chat request to an OpenAI-compatible endpoint. Standard library only.

Settings live in providers.py; this file only sends and reads.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from generator.llm._scrub import short as _short
from generator.llm.providers import LLMConfig, config_from_env

MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class LLMError(RuntimeError):
    """The endpoint was reached but did not give a usable answer."""

    def __init__(self, message: str, status: int | None = None):
        self.status = status
        super().__init__(message)


def chat(messages: list[dict], config: LLMConfig | None = None,
         max_tokens: int = 4096) -> str:
    """Send one chat request and return the text of the first choice."""
    cfg = config or config_from_env()
    payload: dict = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if cfg.thinking:
        payload["thinking"] = {"type": cfg.thinking}
    if cfg.reasoning_effort:
        payload["reasoning_effort"] = cfg.reasoning_effort
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg.key:
        headers["Authorization"] = f"Bearer {cfg.key}"
    req = urllib.request.Request(cfg.endpoint, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        detail = _short(e.read() or b"", cfg.key)
        raise LLMError(f"endpoint answered {e.code}: {detail}", status=e.code) from None
    except (socket.timeout, TimeoutError):
        raise LLMError(f"no answer within {cfg.timeout:g}s") from None
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise LLMError(f"no answer within {cfg.timeout:g}s") from None
        raise LLMError(f"endpoint not reachable: {reason}") from None

    if len(raw) > MAX_RESPONSE_BYTES:
        raise LLMError("answer larger than 5 MB")
    try:
        data = json.loads(raw)
        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise LLMError(f"answer is not a chat completion: {_short(raw, cfg.key)}") from None
    if not isinstance(content, str) or not content.strip():
        raise LLMError("answer has no text (" + _why_empty(data, choice, message) + ")")
    return content


def _why_empty(data: dict, choice: dict, message: dict) -> str:
    """Facts that explain an empty answer, without any of its content."""
    facts = [f"finish_reason={choice.get('finish_reason')}"]
    usage = data.get("usage") or {}
    if isinstance(usage, dict):
        for k in ("prompt_tokens", "completion_tokens"):
            if k in usage:
                facts.append(f"{k}={usage[k]}")
        details = usage.get("completion_tokens_details") or {}
        if isinstance(details, dict) and "reasoning_tokens" in details:
            facts.append(f"reasoning_tokens={details['reasoning_tokens']}")
    reasoning = message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        facts.append(f"reasoning_content of {len(reasoning)} chars")
    if choice.get("finish_reason") == "length":
        facts.append("the token limit ran out before the answer")
    return ", ".join(facts)
