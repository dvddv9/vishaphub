# -*- coding: utf-8 -*-
"""FastAPI auth dependencies: Clerk users, tenants, manual-billing API keys."""
import os
from datetime import UTC, datetime

from fastapi import Header, HTTPException

from src.api.job_store import DEFAULT_TENANT
from src.api.tenants import (
    API_KEY_PREFIX,
    STATUS_ACTIVE,
    get_tenant_by_api_key,
)
from src.auth.clerk import AuthError, verify_jwt
from src.observability.logging import get_logger

log = get_logger(__name__)

#: Fallback tenant for requests that authenticate with an API key, not Clerk.
_FALLBACK_TENANT = os.getenv("VISHAP_DEFAULT_TENANT", DEFAULT_TENANT)


def _claims_to_identity(claims: dict) -> dict:
    """Map Clerk claims to the tenant-scoped identity used by the API."""
    user_id = claims["sub"]
    return {
        "user_id": user_id,
        # Clerk org membership wins; personal accounts fall back to the user id.
        "tenant_id": claims.get("org_id") or user_id,
        "claims": claims,
    }


async def current_user(authorization: str | None = Header(None)) -> dict:
    """Resolve the current user from a Clerk `Authorization: Bearer <jwt>` header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:]
    try:
        claims = verify_jwt(token)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return _claims_to_identity(claims)


async def current_tenant(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None),
) -> str:
    """Tenant for endpoints that accept either a Clerk JWT or an API key.

    * Bearer token present: it must verify, otherwise 401. A bad or expired token used
      to fall back silently to the default tenant, i.e. it opened that tenant's data.
    * No Bearer token: the request passes the same gate as the write endpoints
      (:func:`src.api.auth.verify_api_key`: static key, tenant key, or an explicitly
      open deployment such as VISHAP_PUBLIC_DEMO) and shares the default tenant, since
      an API key carries no identity.
    """
    if authorization and authorization.startswith("Bearer "):
        try:
            claims = verify_jwt(authorization[7:])
        except AuthError as e:
            raise HTTPException(status_code=401, detail=str(e))
        return claims.get("org_id") or claims.get("sub") or _FALLBACK_TENANT
    from src.api.auth import verify_api_key

    await verify_api_key(x_api_key or "")
    return _FALLBACK_TENANT


def _as_datetime(value) -> datetime | None:
    """Normalise an ISO string (or datetime) to an aware datetime."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def verify_tenant_api_key(x_api_key: str | None = Header(None)) -> dict:
    """Validate a tenant-issued API key and return the tenant row.

    Used for customers billed by bank transfer: the key comes from
    ``scripts/generate_key.py`` and carries its own expiry.

    Three rules matter here, because this runs on the authentication path:

    * a key that does not carry our prefix is rejected without a database
      round-trip — arbitrary input must not cost a connection;
    * a store failure (no ``DATABASE_URL``, Postgres down, migration not
      applied) is a **401**, never a 500: an auth check that raises turns every
      request into an outage;
    * a failure is never a success — fail closed.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")

    if not x_api_key.startswith(API_KEY_PREFIX):
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        tenant = await get_tenant_by_api_key(x_api_key)
    except Exception as exc:  # TenantStoreError, OperationalError, InterfaceError
        log.warning("tenant_key_lookup_failed", error=str(exc))
        raise HTTPException(status_code=401, detail="Invalid API key") from exc

    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if tenant.get("status") != STATUS_ACTIVE:
        raise HTTPException(status_code=401, detail=f"Tenant status: {tenant.get('status')}")

    expires_at = _as_datetime(tenant.get("expires_at"))
    if expires_at is not None and expires_at < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="API key expired")

    return tenant
