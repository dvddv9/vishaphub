# -*- coding: utf-8 -*-
"""Lemon Squeezy webhook handler (HMAC + idempotency + tenant updates)."""
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import Column, DateTime, String, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.job_store_postgres import Base
from src.api.tenants import STATUS_ACTIVE, STATUS_CANCELED, TenantModel
from src.observability.logging import get_logger

log = get_logger(__name__)


class ProcessedWebhookEvent(Base):
    """Idempotency: LS retries webhooks; never double-apply."""

    __tablename__ = "processed_webhook_events"

    event_id: str = Column(String(128), primary_key=True)
    event_name: str = Column(String(64), nullable=False)
    processed_at: datetime = Column(DateTime(timezone=True), nullable=False)


_ACTIVATE_EVENTS = frozenset({
    "order_created",
    "subscription_created",
    "subscription_resumed",
    "subscription_unpaused",
})
_DEACTIVATE_EVENTS = frozenset({
    "subscription_cancelled",
    "subscription_expired",
    "subscription_paused",
})


def _verify_signature(payload: bytes, signature: str) -> None:
    secret = os.getenv("dvddvdvdvdvd", "")
    if not secret:
        raise HTTPException(status_code=500, detail="LEMONSQUEEZY_WEBHOOK_SECRET not set")
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


async def handle_lemonsqueezy_webhook(
    payload: bytes, signature: str, session: AsyncSession
) -> dict:
    """Verify HMAC, dedupe by event_id, apply tenant status changes."""
    _verify_signature(payload, signature)

    try:
        event = json.loads(payload)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    meta = event.get("meta", {})
    event_id = meta.get("event_id")
    event_name = meta.get("event_name")
    custom = meta.get("custom_data") or {}
    tenant_id = custom.get("tenant_id")

    if not event_id:
        raise HTTPException(status_code=400, detail="Missing meta.event_id")

    existing = await session.get(ProcessedWebhookEvent, event_id)
    if existing is not None:
        log.info("ls_webhook_duplicate", event_id=event_id, event_name=event_name)
        return {"status": "ok", "event": event_name, "duplicate": True}

    data = event.get("data", {})
    attrs = data.get("attributes", {}) or {}
    customer_id = attrs.get("customer_id") or attrs.get("user_id")

    applied = False
    if tenant_id and event_name in _ACTIVATE_EVENTS:
        values = {"status": STATUS_ACTIVE}
        if customer_id is not None:
            values["ls_customer_id"] = str(customer_id)
        stmt = update(TenantModel).where(TenantModel.tenant_id == tenant_id).values(**values)
        result = await session.execute(stmt)
        applied = result.rowcount > 0
        log.info(
            "ls_webhook_activate",
            tenant_id=tenant_id,
            customer_id=customer_id,
            event_name=event_name,
            applied=applied,
        )
    elif tenant_id and event_name in _DEACTIVATE_EVENTS:
        stmt = update(TenantModel).where(TenantModel.tenant_id == tenant_id).values(status=STATUS_CANCELED)
        result = await session.execute(stmt)
        applied = result.rowcount > 0
        log.info(
            "ls_webhook_deactivate",
            tenant_id=tenant_id,
            event_name=event_name,
            applied=applied,
        )
    elif event_name in (_ACTIVATE_EVENTS | _DEACTIVATE_EVENTS):
        log.warning("ls_webhook_missing_tenant", event_id=event_id, event_name=event_name)

    session.add(
        ProcessedWebhookEvent(
            event_id=event_id,
            event_name=event_name or "unknown",
            processed_at=datetime.now(UTC),
        )
    )
    await session.commit()

    return {"status": "ok", "event": event_name, "applied": applied}