# -*- coding: utf-8 -*-
"""Audit webhook tests (v6.3) — httpx is mocked, nothing leaves the process."""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.api import webhooks


class _FakeClient:
    """Minimal stand-in for httpx.AsyncClient used as an async context manager."""

    calls: list = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, json=None):
        _FakeClient.calls.append((url, json))
        return MagicMock(status_code=200)


class _TimeoutClient(_FakeClient):
    async def post(self, url, json=None):
        raise httpx.TimeoutException("timed out")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    _FakeClient.calls = []
    monkeypatch.delenv("VISHAP_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(webhooks, "VISHAP_WEBHOOK_URL", "")


@pytest.mark.asyncio
async def test_webhook_noop_if_not_configured():
    delivered = await webhooks.notify_webhook("job.completed", {"job_id": "j1"})
    assert delivered is False


@pytest.mark.asyncio
async def test_webhook_sends_event(monkeypatch):
    monkeypatch.setenv("VISHAP_WEBHOOK_URL", "https://siem.test/hook")
    with patch.object(webhooks.httpx, "AsyncClient", _FakeClient):
        delivered = await webhooks.notify_webhook("job.completed", {"job_id": "j1"})

    assert delivered is True
    assert _FakeClient.calls == [
        ("https://siem.test/hook", {"event": "job.completed", "data": {"job_id": "j1"}})
    ]


@pytest.mark.asyncio
async def test_webhook_handles_timeout(monkeypatch):
    monkeypatch.setenv("VISHAP_WEBHOOK_URL", "https://siem.test/hook")
    with patch.object(webhooks.httpx, "AsyncClient", _TimeoutClient):
        delivered = await webhooks.notify_webhook("job.failed", {"job_id": "j1"})

    assert delivered is False  # swallowed, never raised
