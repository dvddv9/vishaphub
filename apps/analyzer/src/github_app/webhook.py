# -*- coding: utf-8 -*-
"""GitHub webhook handler (v6.1)."""
import hashlib
import hmac
import os

from fastapi import HTTPException, Request

from src.github_app.client import (
    analyze_pr_diff,
    get_installation_token,
    post_pr_comment,
)


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub's X-Hub-Signature-256 (HMAC SHA256)."""
    if not secret or not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _format_comment(result: dict) -> str:
    verdict = result.get("verdict", "SAFE")
    findings = result.get("findings") or []
    lines = [f"## Vishap — {verdict}"]
    for f in findings[:20]:
        if isinstance(f, dict):
            lines.append(
                f"- **{f.get('id', '?')}** ({f.get('priority', '?')}): {f.get('title', '')}"
            )
    return "\n".join(lines)


async def handle_webhook(request: Request) -> dict:
    """Handle a GitHub webhook: verify signature, dispatch by event."""
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    signature = request.headers.get("X-Hub-Signature-256", "")
    payload = await request.body()

    if not verify_signature(payload, signature, secret):
        raise HTTPException(status_code=403, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    data = await request.json()

    if event == "ping":
        return {"ok": True}

    if event == "pull_request" and data.get("action") == "opened":
        repo = (data.get("repository") or {}).get("full_name", "")
        pr_number = data.get("number") or (data.get("pull_request") or {}).get("number")
        installation_id = (data.get("installation") or {}).get("id")
        token = get_installation_token(installation_id) if installation_id else ""
        result = analyze_pr_diff(repo, pr_number, token)
        post_pr_comment(repo, pr_number, _format_comment(result), token)
        return {"ok": True, "triggered": True, "verdict": result.get("verdict", "SAFE")}

    return {"ok": True, "ignored": True}
