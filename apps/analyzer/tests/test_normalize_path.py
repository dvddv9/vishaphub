# -*- coding: utf-8 -*-
"""Behaviour of vercel/sandbox `normalizePath` (CWE-22 analysis, v6.5).

These tests exercise a Python port of the real TypeScript function
(``scripts/normalize_path.py``); the first test pins the port to the upstream
vitest expectations so the analysis cannot drift from the implementation.

What the tests establish, and what they deliberately do **not** establish:
``normalizePath`` does not block ``..`` — it resolves it against ``cwd`` and
returns a name relative to ``extractDir``. Whether that name is dangerous is a
server-side question; see ``docs/security/vercel-sandbox-path-traversal.md``.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from normalize_path import UPSTREAM_TESTS, normalize_path  # noqa: E402


def test_matches_upstream_vitest_expectations():
    for file_path, cwd, extract_dir, expected in UPSTREAM_TESTS:
        assert normalize_path(file_path, cwd, extract_dir) == expected, (
            f"port diverged for {file_path!r} with cwd={cwd!r}, extractDir={extract_dir!r}"
        )


def test_normalize_path_traversal():
    """`../..` climbs out of cwd: the returned name is `etc/passwd`."""
    name = normalize_path("../../etc/passwd", cwd="/vercel/sandbox", extract_dir="/")

    assert name == "etc/passwd"
    assert not name.startswith(".."), "the archive name itself carries no '..'"
    assert not name.startswith("/"), "and it is not absolute"


def test_normalize_path_absolute():
    """An absolute input is normalised and re-anchored at extractDir."""
    name = normalize_path("/etc/passwd", cwd="/bar", extract_dir="/")

    assert name == "etc/passwd"
    assert not name.startswith("/")


def test_normalize_path_safe():
    """A plain relative path stays under cwd — note the `vercel/sandbox/` prefix.

    The documentation in the task assumed ``"file.txt"`` normalises to
    ``"file.txt"``. It does not: the result is relative to ``extractDir``, so the
    working directory becomes part of the name.
    """
    name = normalize_path("file.txt", cwd="/vercel/sandbox", extract_dir="/")

    assert name == "vercel/sandbox/file.txt"


def test_escapes_cwd_when_extract_dir_is_the_root():
    """The interesting property: cwd is not a boundary, only extractDir is."""
    assert normalize_path("../secret.txt", cwd="/vercel/sandbox", extract_dir="/") == (
        "vercel/secret.txt"
    )
    assert normalize_path("../../../../etc/passwd", cwd="/vercel/sandbox", extract_dir="/") == (
        "etc/passwd"
    )


def test_can_return_a_dotdot_prefixed_name():
    """When extractDir is not an ancestor, the tarball entry itself starts with `..`.

    This is the case upstream marks "TODO: Should this be allowed?" — and it is
    the only shape in which a `..` component actually reaches the archive.
    """
    name = normalize_path("bar.txt", cwd="/", extract_dir="/vercel")

    assert name == "../bar.txt"
    assert name.startswith("..")


def test_rejects_relative_roots():
    with pytest.raises(ValueError, match="cwd dir must be absolute"):
        normalize_path("x", cwd="relative/root", extract_dir="/")
    with pytest.raises(ValueError, match="extractDir must be absolute"):
        normalize_path("x", cwd="/", extract_dir="some/relative/path")
