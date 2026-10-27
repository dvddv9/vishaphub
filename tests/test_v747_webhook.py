# -*- coding: utf-8 -*-
"""v7.4.7: Lemon Squeezy webhook reads LEMONSQUEEZY_WEBHOOK_SECRET; refunds revoke access."""
import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.tenants import STATUS_ACTIVE, STATUS_CANCELED
from src.billing.lemonsqueezy import webhook

SECRET = "whsec_test"


def _sig(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


class _Session:
    def __init__(self):
        self.statements = []

    async def get(self, _model, _key):
        return None

    async def execute(self, stmt):
        self.statements.append(stmt)
        return SimpleNamespace(rowcount=1)

    def add(self, _obj):
        pass

    async def commit(self):
        pass


def _event(name, event_id="e1"):
    return json.dumps({
        "meta": {"event_name": name, "event_id": event_id, "custom_data": {"tenant_id": "t1"}},
        "data": {"attributes": {"customer_id": 7}},
    }).encode()


def _status_set(session):
    return [s.compile().params.get("status") for s in session.statements]


def test_secret_is_read_from_documented_name(monkeypatch):
    monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", SECRET)
    body = _event("order_created")
    webhook._verify_signature(body, _sig(body))
    with pytest.raises(HTTPException) as e:
        webhook._verify_signature(body, "0" * 64)
    assert e.value.status_code == 401


def test_missing_secret_is_500_not_a_pass(monkeypatch):
    monkeypatch.delenv("LEMONSQUEEZY_WEBHOOK_SECRET", raising=False)
    body = _event("order_created")
    with pytest.raises(HTTPException) as e:
        webhook._verify_signature(body, _sig(body))
    assert e.value.status_code == 500


@pytest.mark.parametrize("name", ["order_refunded", "subscription_payment_refunded"])
def test_refund_revokes_access(monkeypatch, name):
    monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", SECRET)
    body = _event(name)
    s = _Session()
    out = asyncio.run(webhook.handle_lemonsqueezy_webhook(body, _sig(body), s))
    assert out["applied"] is True
    assert _status_set(s) == [STATUS_CANCELED]


def test_order_created_still_activates(monkeypatch):
    monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", SECRET)
    body = _event("order_created", "e2")
    s = _Session()
    asyncio.run(webhook.handle_lemonsqueezy_webhook(body, _sig(body), s))
    assert _status_set(s) == [STATUS_ACTIVE]
