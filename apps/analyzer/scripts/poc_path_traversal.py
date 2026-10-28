#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PoC: what vercel/sandbox puts in the tarball for `../..` paths (v6.5).

Mock only. This builds a real gzipped tar with :mod:`tarfile` using the exact
name that ``normalizePath`` produces, then re-opens the archive and prints its
member names. The Vercel API is never contacted and nothing is extracted, so no
file is written anywhere.

Run: ``python scripts/poc_path_traversal.py``
"""
import io
import posixpath
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from normalize_path import normalize_path  # noqa: E402

#: (declared path, cwd, extractDir) — the first is the case from the report.
CASES = (
    ("../../etc/passwd", "/vercel/sandbox", "/"),
    ("/etc/passwd", "/bar", "/"),
    ("bar.txt", "/", "/vercel"),
)


def build_tarball(entries: list[tuple[str, str]]) -> io.BytesIO:
    """Pack (name, content) pairs into a gzipped tar, exactly like FileWriter."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in entries:
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    buffer.seek(0)
    return buffer


def member_names(buffer: io.BytesIO) -> list[str]:
    buffer.seek(0)
    with tarfile.open(fileobj=buffer, mode="r:gz") as archive:
        return [member.name for member in archive.getmembers()]


def main() -> int:
    print("normalizePath -> tar entry name (mock, no Vercel API)\n")
    risky: list[str] = []

    for file_path, cwd, extract_dir in CASES:
        name = normalize_path(file_path, cwd, extract_dir)
        members = member_names(build_tarball([(name, "payload")]))
        entry = members[0]
        escapes = ".." in entry.split("/")
        lands_at = posixpath.normpath(posixpath.join(extract_dir, entry))

        print(f"  declared : {file_path}")
        print(f"  cwd      : {cwd}   extractDir: {extract_dir}")
        print(f"  name     : {name}")
        print(f"  tarball  : {members}")
        print(f"  contains '..' component: {escapes}")
        print(f"  extracted at extractDir -> {lands_at}")
        print()

        if escapes:
            risky.append(entry)

    print("Verdict")
    print("-------")
    print(
        "1. '../../etc/passwd' becomes 'etc/passwd': the '..' is folded away "
        "client-side\n   and the archive entry is relative with no '..' component."
    )
    print(
        "   -> the chain 'writeFile(\"../../etc/passwd\") writes the host's "
        "/etc/passwd'\n      is NOT reproduced by this code path."
    )
    print(
        "2. normalizePath does not confine the name to cwd - it escapes upward "
        "until it\n   hits extractDir. With extractDir='/' that is the sandbox "
        "root, not the host."
    )
    print(
        f"3. A '..' component CAN reach the archive, but only when extractDir is "
        f"not an\n   ancestor of the path (e.g. extractDir='/vercel', cwd='/'). "
        f"Observed: {risky or 'none'}"
    )
    print(
        "   -> exploitability then depends on the server's extractor rejecting "
        "'..' entries,\n      which is not observable from this repository."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
