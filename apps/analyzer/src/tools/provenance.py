# -*- coding: utf-8 -*-
"""Provenance tracking — where the material came from.

Dogfood P2: trust boundary for material depends on source.
- CI/GitHub PR -> untrusted
- Production -> trusted
- Manual -> unknown
"""
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _run_git(args: list, cwd: str = None) -> str:
    """Run git command, return stdout stripped, or empty on error."""
    try:
        r = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=5,
            cwd=cwd or os.getcwd(),
            encoding="utf-8", errors="replace",
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def detect_source() -> str:
    """Detect source of material.

    Returns:
        "ci/github", "ci/gitlab", "ci/generic", "git/<branch>", "manual"
    """
    if os.getenv("GITHUB_ACTIONS") == "true":
        return "ci/github"
    if os.getenv("GITLAB_CI") == "true":
        return "ci/gitlab"
    if os.getenv("CI") == "true" or os.getenv("CI"):
        return "ci/generic"

    # Check if we're in a git repo
    if Path(".git").exists() or _run_git(["rev-parse", "--git-dir"]):
        branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
        return f"git/{branch}"

    return "manual"


def get_provenance(cwd: str = None) -> dict:
    """Collect provenance info.

    Returns:
        {
            "source": str,
            "git_commit": str (40-hex or ""),
            "git_commit_short": str (7-hex or ""),
            "git_branch": str,
            "git_author": str,
            "git_author_email": str,
            "git_remote": str,
            "ci_run_id": str,
            "ci_pr_number": str,
            "timestamp": str (ISO 8601 UTC),
        }
    """
    prov = {
        "source": detect_source(),
        "git_commit": "",
        "git_commit_short": "",
        "git_branch": "",
        "git_author": "",
        "git_author_email": "",
        "git_remote": "",
        "ci_run_id": "",
        "ci_pr_number": "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Git info
    commit = _run_git(["rev-parse", "HEAD"], cwd=cwd)
    if commit:
        prov["git_commit"] = commit
        prov["git_commit_short"] = commit[:7]

    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    if branch:
        prov["git_branch"] = branch

    author = _run_git(["log", "-1", "--format=%an"], cwd=cwd)
    if author:
        prov["git_author"] = author

    email = _run_git(["log", "-1", "--format=%ae"], cwd=cwd)
    if email:
        prov["git_author_email"] = email

    remote = _run_git(["config", "--get", "remote.origin.url"], cwd=cwd)
    if remote:
        prov["git_remote"] = remote

    # CI info
    if prov["source"] == "ci/github":
        prov["ci_run_id"] = os.getenv("GITHUB_RUN_ID", "")
        # PR number from GITHUB_REF
        ref = os.getenv("GITHUB_REF", "")
        if ref.startswith("refs/pull/"):
            prov["ci_pr_number"] = ref.split("/")[2]

    return prov


def provenance_summary(prov: dict) -> str:
    """Human-readable summary for [AUDIT_TRAIL]."""
    src = prov.get("source", "unknown")
    commit = prov.get("git_commit_short", "")
    branch = prov.get("git_branch", "")
    parts = [src]
    if commit:
        parts.append(f"commit:{commit}")
    if branch:
        parts.append(f"branch:{branch}")
    return " ".join(parts)
