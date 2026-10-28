# -*- coding: utf-8 -*-
"""GitHub API client (v6.1)."""
import httpx

from src.github_app.auth import generate_jwt

GITHUB_API = "https://api.github.com"


def _headers(token: str, accept: str = "application/vnd.github+json") -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": accept}


def get_installation_token(installation_id: int) -> str:
    """Exchange the App JWT for an installation access token."""
    jwt_token = generate_jwt()
    r = httpx.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers=_headers(jwt_token),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["token"]


def post_pr_comment(repo: str, pr_number: int, body: str, token: str) -> dict:
    """Post a comment on a pull request (as an issue comment)."""
    r = httpx.post(
        f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments",
        headers=_headers(token),
        json={"body": body},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def analyze_pr_diff(repo: str, pr_number: int, token: str) -> dict:
    """Fetch the PR diff and run the Vishap pipeline; return a compact result."""
    r = httpx.get(
        f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
        headers=_headers(token, accept="application/vnd.github.v3.diff"),
        timeout=10,
    )
    r.raise_for_status()
    diff = r.text

    from src.pipeline.orchestrator import run_pipeline

    result = run_pipeline(diff, f"PR-{pr_number}.diff", verbose=False)
    audit = result.get("audit", {}) or {}
    stage2 = result.get("stage2", {}) or {}
    sec = stage2.get("security", {}) if isinstance(stage2.get("security"), dict) else {}
    return {
        "verdict": audit.get("risk_verdict", "SAFE"),
        "findings": sec.get("findings", []),
        "session_id": result.get("session_id", ""),
        "final_markdown": result.get("final_markdown", ""),
    }
