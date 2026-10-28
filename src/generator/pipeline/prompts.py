"""Load the prompt files and wrap data for the model."""

from __future__ import annotations

import secrets
from functools import lru_cache

from generator.config import PROMPTS_DIR

RULES = "00_rules"


@lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    """The text of prompts/<name>.md."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def system_prompt(name: str) -> str:
    """A stage prompt followed by the rules every stage shares."""
    return load_prompt(name).rstrip() + "\n\n" + load_prompt(RULES).strip() + "\n"


def wrap_data(label: str, text: str) -> str:
    """Put untrusted text between markers nobody can guess.

    The tag is new on every call, so the text cannot contain the closing marker.
    """
    tag = f"VG_{label}_{secrets.token_hex(8)}"
    return f"<{tag}>\n{text}\n</{tag}>"
