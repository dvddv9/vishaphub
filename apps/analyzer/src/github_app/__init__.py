# -*- coding: utf-8 -*-
"""GitHub App integration package (v6.1)."""
from src.github_app.auth import generate_jwt
from src.github_app.client import (
    analyze_pr_diff,
    get_installation_token,
    post_pr_comment,
)
from src.github_app.webhook import handle_webhook, verify_signature

__all__ = [
    "generate_jwt",
    "get_installation_token",
    "post_pr_comment",
    "analyze_pr_diff",
    "handle_webhook",
    "verify_signature",
]
