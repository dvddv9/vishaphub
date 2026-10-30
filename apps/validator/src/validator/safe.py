"""What the code under test may see and reach.

The validator runs the deliverable's own tests and imports its entry point. That is executing someone
else's code, so two things are decided here and nowhere else: the environment it gets, and which paths a
spec may name.
"""
from __future__ import annotations

import os
import re

#: The only variables the code under test inherits. Nothing else: the host's keys, database URLs and
#: tokens live in its environment, and a test that prints `os.environ` would otherwise print them.
_KEEP = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL")

#: A dotted Python name. Anything else (a path, a `;`, a space) is not an entry point.
ENTRY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def clean_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _KEEP if key in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def escapes(root: str, rel: object) -> bool:
    """True if `rel` is not a path that stays inside `root` (absolute, `..`, NUL, empty, not a string)."""
    if not isinstance(rel, str) or not rel or "\x00" in rel:
        return True
    if os.path.isabs(rel) or rel.startswith(("/", "\\")):
        return True
    base = os.path.realpath(root)
    try:
        return os.path.commonpath([base, os.path.realpath(os.path.join(base, rel))]) != base
    except ValueError:  # another drive on Windows
        return True


def spec_problems(root: str, spec) -> list[str]:
    """What in the spec points outside the deliverable. Empty means the spec may be used."""
    problems = [f"{field} path is outside the deliverable: {rel!r}"
                for field in ("files", "tests") for rel in getattr(spec, field)
                if escapes(root, rel)]
    entry = spec.entry
    if entry and not (isinstance(entry, str) and ENTRY.fullmatch(entry)):
        problems.append(f"entry is not a dotted module name: {entry!r}")
    return problems