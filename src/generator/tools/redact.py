"""Redact secrets from text before it goes to the model.

The analog of Vishap's `tools/redact.py` (pre-LLM redaction). A spec is free text written by a person, and a person
sometimes pastes a key into it. The model is a third party, so keys, tokens, private keys and passwords in
connection strings are replaced with `[REDACTED:<kind>]` before the text leaves. Only secrets are redacted by
default; email addresses (personal data, and often just examples in a spec) only with `pii=True`.

The patterns are deliberately narrow: a rule like "token: expires in 5 minutes" is prose, not a secret, and
must reach the model unchanged. Nothing here is a guarantee: it catches the common shapes of keys, not every
secret a person can type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_VALUE = r"""(?=[^\s"',;]*\d)(?=[^\s"',;]*[A-Za-z])[^\s"',;]{12,}"""

# (kind, pattern, replacement); the replacement may keep a group (the name of the field)
PATTERNS: tuple[tuple[str, re.Pattern, str], ...] = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "[REDACTED:private-key]"),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED:aws-key]"),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})\b"),
     "[REDACTED:github-token]"),
    ("api-key", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{30,}"
                          r"|xox[baprs]-[A-Za-z0-9-]{10,})"), "[REDACTED:api-key]"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "[REDACTED:jwt]"),
    ("bearer", re.compile(r"(?i)\b(Bearer)\s+[A-Za-z0-9._~+/=-]{16,}"), r"\1 [REDACTED:bearer]"),
    ("url-password", re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]+):([^/\s@]+)@"),
     r"\1\2:[REDACTED:password]@"),
    ("assigned-secret", re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?key|token)\b"
                                   r"(\s*[:=]\s*[\"']?)(" + _VALUE + r")"), r"\1\2[REDACTED:secret]"),
)
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")


@dataclass(frozen=True)
class RedactResult:
    text: str
    applied: tuple[tuple[str, int], ...]      # (kind, how many), never the values

    def to_dict(self) -> dict:
        return {kind: n for kind, n in self.applied}


def redact(text: str, *, pii: bool = False) -> RedactResult:
    counts: dict[str, int] = {}
    for kind, pattern, repl in PATTERNS:
        text, n = pattern.subn(repl, text)
        if n:
            counts[kind] = counts.get(kind, 0) + n
    if pii:
        text, n = EMAIL.subn("[REDACTED:email]", text)
        if n:
            counts["email"] = n
    return RedactResult(text, tuple(sorted(counts.items())))


def is_redacted(text: str) -> bool:
    return "[REDACTED:" in text
