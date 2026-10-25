# -*- coding: utf-8 -*-
"""Lemon Squeezy client (checkout URL)."""
import os

import httpx

LS_API_URL = "https://api.lemonsqueezy.com/v1"


def _headers() -> dict:
    key = os.getenv("LEMONSQUEEZY_API_KEY", "")
    if not key:
        raise RuntimeError("LEMONSQUEEZY_API_KEY not set")
    return {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "Authorization": f"Bearer {key}",
    }


async def create_checkout_url(email: str, variant_id: str, tenant_id: str) -> str:
    store_id = os.getenv("LEMONSQUEEZY_STORE_ID", "")
    if not store_id:
        raise RuntimeError("LEMONSQUEEZY_STORE_ID not set")
    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email": email,
                    "custom": {"tenant_id": tenant_id},
                },
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": store_id}},
                "variant": {"data": {"type": "variants", "id": variant_id}},
            },
        }
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{LS_API_URL}/checkouts", headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()["data"]["attributes"]["url"]