# -*- coding: utf-8 -*-
"""SMTP delivery tests (v6.5) — smtplib is mocked, nothing leaves the process."""
from unittest.mock import MagicMock, patch

import pytest

from src.notifications import email

_SMTP_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM")


@pytest.fixture(autouse=True)
def _clean_smtp(monkeypatch):
    for name in _SMTP_VARS:
        monkeypatch.delenv(name, raising=False)


def _smtp_server() -> MagicMock:
    server = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=server)
    ctx.__exit__ = MagicMock(return_value=False)
    return server, ctx


def test_send_email_uses_smtp(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "bot@vishap.dev")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")

    server, ctx = _smtp_server()
    with patch.object(email.smtplib, "SMTP", return_value=ctx) as smtp_cls:
        sent = email.send_email("client@example.com", "Renewal reminder", "Body text")

    assert sent is True
    smtp_cls.assert_called_once_with(
        "smtp.example.com", 587, timeout=email.TIMEOUT_SECONDS
    )
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("bot@vishap.dev", "secret")

    message = server.send_message.call_args[0][0]
    assert message["To"] == "client@example.com"
    assert message["Subject"] == "Renewal reminder"
    assert message["From"] == "bot@vishap.dev"  # SMTP_FROM falls back to SMTP_USER


def test_send_email_skips_without_config(capsys):
    with patch.object(email.smtplib, "SMTP") as smtp_cls:
        sent = email.send_email("client@example.com", "Subject", "Body")

    assert sent is False
    smtp_cls.assert_not_called()
    assert "SMTP not configured" in capsys.readouterr().out
