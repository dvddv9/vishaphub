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
    with patch("src.github_app.client.httpx.get") as get, \
         patch("src.github_app.client.httpx.post") as post:
        get.return_value = MagicMock(status_code=200)
        get.return_value.json.return_value = []
        post.return_value = MagicMock(status_code=201)
        post.return_value.json.return_value = {"id": 1, "body": "hi"}
        result = post_pr_comment("owner/repo", 42, "hi", "t0ken")
    assert result["id"] == 1
    get.assert_called_once()
    post.assert_called_once()


def test_analyze_pr_diff():
    pr = MagicMock(status_code=200)
    pr.json.return_value = {"head": {"sha": "abc123"}}
    diff = MagicMock(status_code=200, text="diff", content=b"diff")
    response = MagicMock()
    response.iter_bytes.return_value = iter([b"archive"])
    stream_context = MagicMock()
    stream_context.__enter__.return_value = response
    with patch("src.github_app.client.httpx.get", side_effect=[pr, diff]) as get, \
         patch("src.github_app.client.httpx.stream", return_value=stream_context), \
         patch("src.github_app.client._extract_snapshot", return_value=1), \
         patch("src.tools.repo_scan.scan_diff", return_value={"findings": [{"id": "SEC-1", "severity": "high"}]}):
        result = analyze_pr_diff("owner/repo", 7, "t0ken")
    assert result["verdict"] == "FAIL"
    assert result["findings"][0]["id"] == "SEC-1"
    assert get.call_count == 2
