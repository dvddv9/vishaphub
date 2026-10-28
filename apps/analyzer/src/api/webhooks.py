# -*- coding: utf-8 -*-
"""Outbound audit webhook (v6.3): job lifecycle events for SIEM/compliance.

Configure ``VISHAP_WEBHOOK_URL`` and every job transition is POSTed as
``{"event": "<type>", "data": {...}}``. Deliberately fail-open: no URL is a
no-op, and transport errors are logged and swallowed, so a webhook outage can
never break analysis.
"""
import os

import httpx

from src.config import VISHAP_WEBHOOK_URL
from src.observability.logging import get_logger

log = get_logger(__name__)

#: Keep the call short: the webhook is observability, not part of the pipeline.
WEBHOOK_TIMEOUT_SECONDS = 5.0


def webhook_url() -> str:
    """Resolve the webhook URL.

    The environment is read on every call (not only at import) so tests and
    container restarts can change it without reloading the module.
    """
    return (os.getenv("VISHAP_WEBHOOK_URL", "") or VISHAP_WEBHOOK_URL).strip()


async def notify_webhook(event_type: str, payload: dict) -> bool:
    """POST one audit event. Returns True when it was delivered."""
    url = webhook_url()
    if not url:
        return False

    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
            await client.post(url, json={"event": event_type, "data": payload})
        return True
    except Exception as exc:  # timeout, DNS, TLS, 5xx — all non-fatal
        # NB: `event` is structlog's own keyword; use `event_type` here.
        log.warning("webhook_failed", event_type=event_type, error=str(exc))
        return False
