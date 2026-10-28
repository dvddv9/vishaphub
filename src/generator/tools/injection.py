"""Text in a spec that talks to the model instead of describing the code.

The analog of Vishap's substitution check (`substitution_seen`, SUBST_MAX_ATTEMPTS). A spec reaches the model
only as data between random markers, so such a line cannot take over the run; it is still a finding, because a
spec that says "ignore previous instructions" was either pasted from somewhere it should not have been or written
to attack the run. One or two are reported as critical gaps; `INJECTION_STOP` or more stop the run.

Patterns are narrow on purpose (a spec may say "you are now redirected"); this finds the common phrasings in
English and Russian, not every possible one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from generator.tools.spec import Spec
from generator.tools.spec_text import iter_texts

_FLAGS = re.I | re.U
PATTERNS = tuple(re.compile(p, _FLAGS) for p in (
    r"\bignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+(?:instructions?|rules?|prompts?)",
    r"\bdisregard\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\b",
    r"\bforget\s+(?:all\s+|your\s+)?(?:previous\s+)?(?:instructions?|rules?)\b",
    r"\b(?:reveal|show|print|repeat|output)\s+(?:me\s+)?(?:your|the)\s+(?:system\s+)?(?:prompt|instructions?|api\s+key|key)\b",
    r"\b(?:work|act|respond)\s+in\s+(?:another|a\s+different|developer|dan)\s+mode\b",
    r"\bnew\s+instructions\s*:",
    r"</?\s*(?:system|assistant)\s*>",
    r"\bигнорируй\s+(?:все\s+)?(?:предыдущ\w+|прежн\w+|вышеуказанн\w+)\s+(?:инструкци\w+|правил\w+|указани\w+)",
    r"\bзабудь\s+(?:все\s+)?(?:правила|инструкции|предыдущ\w+)",
    r"\b(?:выведи|покажи|повтори|раскрой)\s+(?:свой\s+|твой\s+)?(?:системн\w+\s+)?(?:промпт|инструкци\w+|ключ)",
    r"\bработай\s+в\s+другом\s+режиме",
    r"\bновые\s+инструкции\s*:",
))
MAX_PHRASE = 80


@dataclass(frozen=True)
class Hit:
    field: str
    line: int | None
    phrase: str


def scan_text(text: str) -> list[str]:
    found = []
    for pattern in PATTERNS:
        for m in pattern.finditer(text):
            found.append(" ".join(m.group(0).split())[:MAX_PHRASE])
    return found


def scan(spec: Spec) -> list[Hit]:
    """Every instruction-like phrase in the spec, in file order of the fields."""
    hits: list[Hit] = []
    for field, line, text in iter_texts(spec):
        hits += [Hit(field, line, phrase) for phrase in scan_text(text)]
    return hits
