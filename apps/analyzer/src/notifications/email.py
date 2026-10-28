# -*- coding: utf-8 -*-
"""Outbound email over SMTP (v6.5).

Configured entirely from the environment: ``SMTP_HOST``, ``SMTP_PORT``,
``SMTP_USER``, ``SMTP_PASSWORD``, ``SMTP_FROM``. Without a host/user/password the
function is a no-op that returns ``False`` — scripts stay runnable on a machine
with no relay (and in CI) instead of raising.

Delivery is synchronous: the callers are CLI scripts (expiry reminders), not
request handlers, so blocking is the simpler and more predictable choice.
"""
import os
import smtplib
from email.mime.text import MIMEText

from src.observability.logging import get_logger

log = get_logger(__name__)

DEFAULT_PORT = 587
TIMEOUT_SECONDS = 10


def smtp_configured() -> bool:
    """True when host, user and password are all present."""
    return bool(
        os.getenv("SMTP_HOST", "").strip()
        and os.getenv("SMTP_USER", "").strip()
        and os.getenv("SMTP_PASSWORD", "").strip()
    )


def _settings() -> dict:
    user = os.getenv("SMTP_USER", "").strip()
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "").strip() or DEFAULT_PORT),
        "user": user,
        "password": os.getenv("SMTP_PASSWORD", "").strip(),
        "sender": os.getenv("SMTP_FROM", "").strip() or user,
    }


def send_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True only on a successful hand-off."""
    if not to:
        log.warning("email_skipped", reason="no_recipient", subject=subject)
        return False

    if not smtp_configured():
        print("[EMAIL] SMTP not configured, skipping")
        log.warning("email_skipped", reason="smtp_not_configured", subject=subject)
        return False

    settings = _settings()
    message = MIMEText(body, _subtype="plain", _charset="utf-8")
    message["Subject"] = subject
    message["From"] = settings["sender"]
    message["To"] = to

    try:
        with smtplib.SMTP(settings["host"], settings["port"], timeout=TIMEOUT_SECONDS) as server:
            server.starttls()
            server.login(settings["user"], settings["password"])
            server.send_message(message)
    except Exception as exc:  # SMTPException, OSError, authentication errors
        print(f"[EMAIL] Failed: {exc}")
        log.warning("email_failed", to=to, subject=subject, error=str(exc))
        return False

    log.info("email_sent", to=to, subject=subject)
    return True
