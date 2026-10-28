# -*- coding: utf-8 -*-
"""Tests for the GitHub API client (v6.1)."""
from unittest.mock import MagicMock, patch

from src.github_app.client import (
    analyze_pr_diff,
    get_installation_token,
    post_pr_comment,
)


def test_get_installation_token():
    with patch("src.github_app.client.generate_jwt", return_value="jwt"), \
         patch("src.github_app.client.httpx.post") as post:
        post.return_value = MagicMock(status_code=201)
        post.return_value.json.return_value = {"token": "t0ken"}
        token = get_installation_token(123)
    assert token == "t0ken"
    post.assert_called_once()


def test_post_pr_comment():
    with patch("src.github_app.client.httpx.post") as post:
        post.return_value = MagicMock(status_code=201)
        post.return_value.json.return_value = {"id": 1, "body": "hi"}
        result = post_pr_comment("owner/repo", 42, "hi", "t0ken")
    assert result["id"] == 1
    post.assert_called_once()


def test_analyze_pr_diff():
    with patch("src.github_app.client.httpx.get") as get, \
         patch("src.pipeline.orchestrator.run_pipeline", return_value={
             "session_id": "s1",
             "audit": {"risk_verdict": "REQUIRES_REVIEW"},
             "stage2": {"security": {"findings": [{"id": "SEC-1"}]}},
             "final_markdown": "md",
         }):
        get.return_value = MagicMock(status_code=200, text="diff")
        result = analyze_pr_diff("owner/repo", 7, "t0ken")
    assert result["verdict"] == "REQUIRES_REVIEW"
    assert result["findings"][0]["id"] == "SEC-1"
