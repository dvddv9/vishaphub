# -*- coding: utf-8 -*-
"""Tests for the GitHub webhook handler (v6.1)."""
import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.main import app
    return TestClient(app)


def _sig(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_webhook_ping(client, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    payload = b'{"zen": "hi"}'
    r = client.post(
        "/webhook/github",
        content=payload,
        headers={
            "X-Hub-Signature-256": _sig("s3cret", payload),
            "X-GitHub-Event": "ping",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_webhook_pr_opened(client, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    payload = json.dumps({
        "action": "opened",
        "number": 7,
        "repository": {"full_name": "owner/repo"},
        "installation": {"id": 99},
    }).encode()
    with patch("src.github_app.webhook.get_installation_token", return_value="tok"), \
         patch("src.github_app.webhook.analyze_pr_diff",
               return_value={"verdict": "REQUIRES_REVIEW", "findings": []}) as ad, \
         patch("src.github_app.webhook.post_pr_comment", return_value={}):
        r = client.post(
            "/webhook/github",
            content=payload,
            headers={
                "X-Hub-Signature-256": _sig("s3cret", payload),
                "X-GitHub-Event": "pull_request",
                "Content-Type": "application/json",
            },
        )
    assert r.status_code == 200
    assert r.json()["triggered"] is True
    ad.assert_called_once()


def test_webhook_bad_signature(client, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    payload = b'{"zen": "hi"}'
    r = client.post(
        "/webhook/github",
        content=payload,
        headers={
            "X-Hub-Signature-256": "sha256=deadbeef",
            "X-GitHub-Event": "ping",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 401


def test_webhook_ignored_action(client, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    payload = json.dumps({"action": "closed", "number": 7}).encode()
    r = client.post(
        "/webhook/github",
        content=payload,
        headers={
            "X-Hub-Signature-256": _sig("s3cret", payload),
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.json().get("ignored") is True
