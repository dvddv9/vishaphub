# -*- coding: utf-8 -*-
"""Diff-aware scan support for Vishap.

Detects files changed since a git ref (or uncommitted) to limit analysis
to changed files in CI. Falls back to empty list on any git error.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _run_git(args: list, repo_root: str = None, timeout: int = 30) -> str:
    """Run git command, return stdout. Empty string on any error."""
    cmd = ["git"] + args
    kwargs = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "errors": "replace",
    }
    if repo_root:
        kwargs["cwd"] = repo_root
    try:
        result = subprocess.run(cmd, check=False, **kwargs)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def _normalize(path: str) -> str:
    """Normalize path to POSIX-style relative form."""
    if not path:
        return ""
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def get_changed_files(base_ref: str = "HEAD~1", repo_root: str = None) -> list:
    """Files changed between base_ref and HEAD.

    Returns relative POSIX paths. Empty list on git error.
    """
    if not base_ref:
        return []
    out = _run_git(["diff", "--name-only", f"{base_ref}...HEAD"], repo_root=repo_root)
    files = [_normalize(line) for line in out.splitlines() if line.strip()]
    return files


def get_uncommitted_files(repo_root: str = None) -> list:
    """Files changed but not committed (staged + unstaged + untracked)."""
    files = set()
    for args in (
        ["diff", "--name-only", "HEAD"],
        ["diff", "--name-only", "--cached"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        out = _run_git(args, repo_root=repo_root)
        for line in out.splitlines():
            if line.strip():
                files.add(_normalize(line))
    return sorted(files)


def get_changed_files_pr(repo_root: str = None) -> list:
    """Changed files in a GitHub Actions PR context.

    Uses GITHUB_BASE_REF env var (default: main).
    """
    base = os.getenv("GITHUB_BASE_REF", "main")
    if not base:
        return []
    return get_changed_files(f"origin/{base}", repo_root=repo_root)


def is_changed(filename: str, changed: list, repo_root: str = None) -> bool:
    """True if filename (path) matches any entry in changed list.

    Matching: exact normalized path, or suffix match for absolute paths
    (e.g. /full/path/to/file.py matches file.py).
    """
    if not changed:
        return False
    norm = _normalize(filename)
    if not norm:
        return False
    changed_norm = {_normalize(c) for c in changed if c}

    # Exact match
    if norm in changed_norm:
        return True

    # Absolute path -> relative suffix
    try:
        p = Path(filename).resolve()
        if repo_root:
            root = Path(repo_root).resolve()
            try:
                rel = str(p.relative_to(root)).replace("\\", "/")
                if rel in changed_norm:
                    return True
            except ValueError:
                pass
    except (OSError, ValueError):
        pass

    # Basename match (fallback): "input.txt" matches any ".../input.txt"
    base = Path(norm).name
    if base and any(Path(c).name == base for c in changed_norm):
        return True

    return False
