# -*- coding: utf-8 -*-
"""Faithful Python port of vercel/sandbox `normalizePath` (v6.5 analysis helper).

Upstream: ``sandbox/packages/vercel-sandbox/src/utils/normalizePath.ts``

    export function normalizePath({filePath, cwd, extractDir}) {
      if (!path.posix.isAbsolute(cwd)) throw ...
      if (!path.posix.isAbsolute(extractDir)) throw ...
      const basePath = path.posix.isAbsolute(filePath)
        ? path.posix.normalize(filePath)
        : path.posix.join(cwd, filePath);
      return path.posix.relative(extractDir, basePath);
    }

The port uses ``posixpath.relpath``, which normalises both arguments exactly like
``path.posix.relative`` does. The upstream vitest cases are reproduced in
``tests/test_normalize_path.py`` so drift between this port and the real
implementation shows up as a failing test.

Used only for analysis and PoC output — Vishap's runtime does not import it.
"""
import posixpath

UPSTREAM_TESTS = (
    # (file_path, cwd, extract_dir, expected)
    ("foo.txt", "/vercel/sandbox", "/", "vercel/sandbox/foo.txt"),
    ("foo/bar/baz.txt", "/vercel/sandbox", "/", "vercel/sandbox/foo/bar/baz.txt"),
    ("bar.txt", "/", "/", "bar.txt"),
    ("/some/other/dir/foo.txt", "/bar", "/", "some/other/dir/foo.txt"),
    ("foo.txt", "/vercel/sandbox", "/vercel", "sandbox/foo.txt"),
    ("bar.txt", "/", "/vercel", "../bar.txt"),          # upstream: "TODO: should this be allowed?"
    ("/resolves/../this/stuff/foo.txt", "/bar", "/", "this/stuff/foo.txt"),
    ("/handles//extra-slashes", "/", "/", "handles/extra-slashes"),
    ("/../../../foo.txt", "/", "/", "foo.txt"),
    ("../../../../foo.txt", "/vercel/sandbox", "/", "foo.txt"),
    ("../foo.txt", "/vercel/sandbox", "/", "vercel/foo.txt"),
)


def normalize_path(file_path: str, cwd: str, extract_dir: str) -> str:
    """Normalise ``file_path`` to a name relative to ``extract_dir``.

    Raises ``ValueError`` when ``cwd`` or ``extract_dir`` is not absolute, which
    mirrors the two ``throw`` statements upstream.

    Note what it does **not** do: it does not reject ``..`` and it does not
    confine the result to ``cwd``. ``..`` is folded away against ``cwd``, so the
    returned name can point above the working directory (still relative to
    ``extract_dir``) or, when ``extract_dir`` is not an ancestor, can itself start
    with ``..``.
    """
    if not posixpath.isabs(cwd):
        raise ValueError("cwd dir must be absolute")
    if not posixpath.isabs(extract_dir):
        raise ValueError("extractDir must be absolute")

    base = (
        posixpath.normpath(file_path)
        if posixpath.isabs(file_path)
        else posixpath.join(cwd, file_path)
    )
    return posixpath.relpath(base, extract_dir)
