# -*- coding: utf-8 -*-
"""GitHub webhook handler (v6.1)."""
import hashlib
import hmac
import os

from src.github_app.client import (
    analyze_pr_diff,
    get_installation_token,
    post_commit_status,
    post_pr_comment,
)


class WebhookError(ValueError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub's X-Hub-Signature-256 (HMAC SHA256)."""
    if not secret or not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _format_comment(result: dict) -> str:
    verdict = result.get("verdict", "SAFE")
    findings = result.get("findings") or []
    gate = result.get("gate") or {}
    lines = [f"## Vishap — {verdict}", "",
             f"**Merge gate:** {'FAILED' if gate.get('failed') else 'PASSED'} "
             f"(blocks at {gate.get('fail_on', 'high')} and above)",
             f"**Files scanned:** {result.get('files_scanned', 'unknown')} · **Findings:** {len(findings)}", ""]
    for f in findings[:20]:
        if isinstance(f, dict):
            lines.append(
                f"- **{f.get('id', '?')}** ({f.get('severity', '?')}) "
                f"`{f.get('file', '?')}:{f.get('line', '?')}`: {f.get('title', '')}"
            )
    if len(findings) > 20:
        lines.append(f"- … and {len(findings) - 20} more finding(s).")
    return "\n".join(lines)


def handle_payload(payload: bytes, event: str, signature: str, secret: str | None = None) -> dict:
    """Verify and dispatch the raw GitHub payload; usable by both the hub and FastAPI."""
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "") if secret is None else secret
    if not verify_signature(payload, signature, secret):
        raise WebhookError(401, "invalid GitHub signature")

    try:
        import json
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise WebhookError(400, "webhook body is not valid JSON") from None
    if not isinstance(data, dict):
        raise WebhookError(400, "webhook JSON must be an object")

    if event == "ping":
        return {"ok": True}

    action = data.get("action")
    if event == "pull_request" and action in {"opened", "reopened", "synchronize", "ready_for_review"}:
        pull = data.get("pull_request") or {}
        if pull.get("draft") and action != "ready_for_review":
            return {"ok": True, "ignored": True, "reason": "draft pull request"}
        repo = (data.get("repository") or {}).get("full_name", "")
        pr_number = data.get("number") or pull.get("number")
        installation_id = (data.get("installation") or {}).get("id")
        token = get_installation_token(installation_id) if installation_id else ""
        head_sha = str((pull.get("head") or {}).get("sha") or "")
        target = pull.get("html_url") or ""
        if head_sha:
            post_commit_status(repo, head_sha, "pending", "Vishap is scanning the pull request", token, target)
        try:
            result = analyze_pr_diff(repo, pr_number, token, head_sha=head_sha)
        except Exception:
            if head_sha:
                post_commit_status(repo, head_sha, "error", "Vishap could not complete the scan", token, target)
            raise
        gate = result.get("gate") or {}
        failed = bool(gate.get("failed"))
        if head_sha:
            blocking = int(gate.get("blocking_findings", 0))
            state = "failure" if failed else "success"
            desc = f"{blocking} finding(s) at or above {gate.get('fail_on', 'high')}" if failed else "No blocking findings"
            post_commit_status(repo, head_sha, state, desc, token, target)
        post_pr_comment(repo, pr_number, _format_comment(result), token)
        return {"ok": True, "triggered": True, "verdict": result.get("verdict", "SAFE"),
                "gate": gate, "head_sha": head_sha}

    return {"ok": True, "ignored": True}


async def handle_webhook(request) -> dict:
    """FastAPI adapter for deployments that expose the standalone analyzer app."""
    payload = await request.body()
    try:
        return handle_payload(payload, request.headers.get("X-GitHub-Event", ""),
                              request.headers.get("X-Hub-Signature-256", ""))
    except WebhookError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
