"""Read the free `text` of the spec against the requirements (needs the model).

Intake never invents a requirement from `text`. This step only reports:
statements in the text that no requirement covers, as gaps of type
`assumption` (severity noted, so they never block the gate by themselves).
The model also sees them in the GAPS section when it writes the code.

The model's answer is not trusted:
- every quote must appear word for word in the text (whitespace and case
  ignored), otherwise the item is dropped; so the model cannot invent a gap
  or smuggle in its own words;
- at most MAX_ITEMS items, each cut to a short length;
- the spec text goes to the model as data between markers.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from generator.pipeline.design import DesignResult
from generator.tools.gaps import Gap
from generator.pipeline.intake import Requirement, Source
from generator.pipeline.stages import parse_json_response
from generator.pipeline.prompts import build_prompt
from generator.tools.redact import redact
from generator.llm import LLMConfig, chat
from generator.tools.spec import Spec

MAX_ITEMS = 8
MAX_LEN = 200
MAX_TOKENS = 2000
PROMPT = "02_design_textcheck"

class TextCheckError(RuntimeError):
    """The model answered, but not with a usable list."""


def _norm(s: str) -> str:
    return " ".join(s.split()).lower()


def build_messages(spec: Spec, requirements: tuple[Requirement, ...]) -> list[dict]:
    lines = ["REQUIREMENTS:"]
    lines += [f"- {r.id} [{r.priority}] {r.text}" for r in requirements] or ["- (none)"]
    system, user = build_prompt(PROMPT, spec.text, "\n".join(lines))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_uncovered(answer: str, text: str) -> tuple[list[tuple[str, str]], int]:
    """Return ([(quote, why)], number of dropped items)."""
    try:
        data = parse_json_response(answer)
    except ValueError as e:
        raise TextCheckError(str(e)) from None
    items = data.get("uncovered")
    if not isinstance(items, list):
        raise TextCheckError('answer must be an object with an "uncovered" list')
    haystack = _norm(text)
    kept, dropped, seen = [], 0, set()
    for it in items:
        if not isinstance(it, dict) or not isinstance(it.get("quote"), str):
            dropped += 1
            continue
        quote = " ".join(it["quote"].split())
        if not quote or _norm(quote) not in haystack or _norm(quote) in seen:
            dropped += 1
            continue
        seen.add(_norm(quote))
        why = it.get("why") if isinstance(it.get("why"), str) else ""
        kept.append((quote[:MAX_LEN], " ".join(why.split())[:MAX_LEN]))
    if len(kept) > MAX_ITEMS:
        dropped += len(kept) - MAX_ITEMS
        kept = kept[:MAX_ITEMS]
    return kept, dropped


def check_text(spec: Spec, requirements: tuple[Requirement, ...], design: DesignResult,
               chat_fn: Callable[..., str] = chat,
               config: LLMConfig | None = None) -> tuple[DesignResult, int]:
    """Return the design with the text gaps added, and how many items were dropped."""
    if not spec.text.strip():
        return design, 0
    answer = chat_fn(build_messages(spec, requirements), config, max_tokens=MAX_TOKENS)
    found, dropped = parse_uncovered(answer, redact(spec.text).text)   # quotes are matched against what the model saw
    line = spec.key_lines.get("text") or 1
    start = len(design.gaps)
    extra = tuple(
        Gap(id=f"G{start + n}", type="assumption", severity="noted",
            text=f'text says "{quote}" but no requirement covers it' + (f" ({why})" if why else ""),
            source=Source("text", line))
        for n, (quote, why) in enumerate(found, 1))
    return DesignResult(files=design.files, gaps=design.gaps + extra), dropped
