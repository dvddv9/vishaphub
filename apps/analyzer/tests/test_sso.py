# -*- coding: utf-8 -*-
"""SAML SSO stub tests (v6.3) — the feature is intentionally not implemented."""
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


def test_sso_login_returns_501():
    from src.main import app

    client = TestClient(app)
    response = client.get("/auth/sso/login", params={"tenant": "org_123"})

    assert response.status_code == 501
    assert "Clerk Enterprise" in response.json()["detail"]


def test_sso_callback_returns_501():
    from src.main import app

    client = TestClient(app)
    response = client.post("/auth/sso/callback", json={"SAMLResponse": "stub"})

    assert response.status_code == 501
    assert "Clerk Enterprise" in response.json()["detail"]


def test_sso_docs_exists():
    doc = ROOT / "docs" / "SSO.md"
    assert doc.exists(), "docs/SSO.md is missing"

    text = doc.read_text(encoding="utf-8")
    assert "Clerk Enterprise" in text
    assert "/auth/sso/login" in text
    assert "SAML" in text
