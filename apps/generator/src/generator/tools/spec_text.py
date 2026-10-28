"""Every piece of free text in a spec, with the line it is on. Shared by the injection and secret checks."""

from __future__ import annotations

from collections.abc import Iterator

from generator.tools.spec import REQUIREMENT_LISTS, Spec


def iter_texts(spec: Spec) -> Iterator[tuple[str, int | None, str]]:
    """(field, line, text) for the `text` field and every string in the requirement lists."""
    yield "text", spec.key_lines.get("text"), spec.text
    for field in REQUIREMENT_LISTS:
        for item, line in spec.items.get(field, []):
            for key in ("name", "rule", "body", "when", "id", "text"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    yield field, line, value
