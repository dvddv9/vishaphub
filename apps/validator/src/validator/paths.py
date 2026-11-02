"""(Copy of hub.paths: the validator does not depend on the hub.) Where a submitted file may be written. One rule, checked on the result, not on the spelling of the input.

The old check (strip leading slashes, refuse ``..`` and absolute paths) let ``D:evil.py`` through on Windows:
it is neither absolute nor starts with ``..``, and joining it onto the temp directory yields ``D:evil.py``, a
file on another drive. Here the joined path itself must stay inside the root, on the same drive.
"""
from __future__ import annotations

import os


def contained(root: str, rel: object, path=os.path) -> str | None:
    """The full path for ``rel`` under ``root``, or None when it names a drive, is empty, or climbs out.

    ``path`` is the path module (``ntpath`` or ``posixpath``); tests use it to check Windows rules anywhere.
    """
    if not isinstance(rel, str) or not rel.strip() or "\x00" in rel:
        return None
    if path.splitdrive(rel)[0]:
        return None
    cleaned = path.normpath(rel).lstrip("\\/")
    if not cleaned or cleaned == ".":
        return None
    base = path.normpath(root)
    target = path.normpath(path.join(base, cleaned))
    if path.splitdrive(target)[0].lower() != path.splitdrive(base)[0].lower():
        return None
    if not target.startswith(base.rstrip("\\/") + path.sep):
        return None
    return target
