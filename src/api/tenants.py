# -*- coding: utf-8 -*-
"""Tenant lifecycle and manual-billing API keys (v6.5).

Two responsibilities live here:

* **Subscriptions** — ``activate_tenant`` / ``deactivate_tenant`` are called by the
  Stripe webhook and flip ``status`` for the row whose ``ls_customer_id``
  matches.
* **Manual billing** — for customers who pay by bank transfer there is no Stripe
  subscription, so ``scripts/generate_key.py`` creates a row directly with an
  ``expires_at`` date, and ``verify_tenant_api_key`` checks it per request.

All functions are async and talk to Postgres through ``DATABASE_URL``. When it is
absent, ``get_store()`` raises :class:`TenantStoreError` — scripts need it, but
``activate_tenant`` degrades to a log line so a webhook cannot fail because the
database is unreachable.
"""
import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, String, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from src.observability.logging import get_logger

from src.api.job_store_postgres import Base
log = get_logger(__name__)

#: Plans Vishap sells. Kept in code so a typo in a script fails here.
PLANS = frozenset({"free", "pro", "enterprise"})

#: Tenant states. Anything other than "active" denies API access.
STATUS_ACTIVE = "active"
STATUS_CANCELED = "canceled"

API_KEY_PREFIX = "vishap_live_"


class TenantStoreError(RuntimeError):
    """Raised when the tenant store cannot be used (usually no DATABASE_URL)."""


class TenantModel(Base):
    """SQLAlchemy model mapping to the ``tenants`` table (revision 004)."""

    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    api_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    api_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    plan: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_ACTIVE)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ls_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return value or None


def tenant_to_dict(model: TenantModel) -> dict:
    """Serialise a tenant row. Datetimes become ISO strings (JSON-friendly)."""
    return {
        "tenant_id": model.tenant_id,
        # No api_key: only the hash is stored, and returning the field invites
        # callers to treat a tenant dict as a credential store.
        "plan": model.plan,
        "status": model.status,
        "email": model.email,
        "created_at": _iso(model.created_at),
        "expires_at": _iso(model.expires_at),
        "ls_customer_id": model.ls_customer_id,
    }


def hash_api_key(api_key: str) -> str:
    """HMAC-SHA256 of an API key, keyed with ``API_KEY_PEPPER``.

    A plain sha256 was used up to v6.5. That is a weak construction for a
    credential: an attacker who reads the table can hash candidate keys offline
    without any secret, and the digest is a shared global constant, so the same
    key always produces the same value everywhere. HMAC with a pepper kept
    outside the database means a dump alone is not enough to test guesses.

    The pepper is required — a missing pepper is a configuration error and must
    fail loudly rather than silently downgrade to the weaker scheme.
    """
    pepper = os.getenv("API_KEY_PEPPER", "")
    if not pepper:
        raise TenantStoreError("API_KEY_PEPPER is not set")
    return hmac.new(pepper.encode("utf-8"), api_key.encode("utf-8"), hashlib.sha256).hexdigest()


def legacy_hash_api_key(api_key: str) -> str:
    """Unkeyed sha256, used only to migrate keys issued before the pepper.

    Never used to *store* a key; it exists so an already-issued key keeps
    working on first use after the upgrade and is then rehashed.
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    """Create a tenant API key: ``vishap_live_`` plus 32 URL-safe bytes."""
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def generate_tenant_id() -> str:
    return f"tenant_{secrets.token_hex(8)}"


class TenantStore:
    """Async Postgres access for the ``tenants`` table."""

    def __init__(self, database_url: str) -> None:
        self._engine = create_async_engine(database_url)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def create(
        self,
        *,
        tenant_id: str,
        api_key: str,
        plan: str,
        email: str,
        status: str = STATUS_ACTIVE,
        expires_at: datetime | None = None,
        ls_customer_id: str | None = None,
    ) -> dict:
        model = TenantModel(
            tenant_id=tenant_id,
            api_key=None,  # plaintext is never persisted
            api_key_hash=hash_api_key(api_key),
            plan=plan,
            status=status,
            email=email,
            created_at=datetime.now(UTC),
            expires_at=expires_at,
            ls_customer_id=ls_customer_id,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()
        log.info("tenant_created", tenant_id=tenant_id, plan=plan)
        return tenant_to_dict(model)

    async def get_by_hash(self, api_key_hash: str) -> dict | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TenantModel).where(TenantModel.api_key_hash == api_key_hash)
            )
            model = result.scalar_one_or_none()
        return tenant_to_dict(model) if model else None

    async def get_by_api_key(self, api_key: str) -> dict | None:
        """Look a tenant up by presenting the key; only its hash hits the query.

        Keys issued before the pepper existed are stored as an unkeyed sha256.
        They are accepted once and immediately rewritten with the HMAC, so a
        deployment does not have to re-issue every customer key by hand.
        """
        tenant = await self.get_by_hash(hash_api_key(api_key))
        if tenant is not None:
            return tenant

        tenant = await self.get_by_hash(legacy_hash_api_key(api_key))
        if tenant is not None:
            await self.set_api_key_hash(tenant["tenant_id"], hash_api_key(api_key))
            log.info("api_key_hash_upgraded", tenant_id=tenant["tenant_id"])
        return tenant

    async def set_api_key_hash(self, tenant_id: str, api_key_hash: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(TenantModel)
                .where(TenantModel.tenant_id == tenant_id)
                .values(api_key_hash=api_key_hash)
            )
            await session.commit()

    async def list_all(self) -> list[dict]:
        async with self._session_factory() as session:
            result = await session.execute(select(TenantModel).order_by(TenantModel.created_at))
            models = result.scalars().all()
        return [tenant_to_dict(m) for m in models]

    async def set_status_by_customer(self, customer_id: str, status: str) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                update(TenantModel)
                .where(TenantModel.ls_customer_id == customer_id)
                .values(status=status)
            )
            await session.commit()
        return result.rowcount or 0

    async def dispose(self) -> None:
        await self._engine.dispose()


_store: TenantStore | None = None


def get_store() -> TenantStore:
    """Return the process-wide store, creating it on first use."""
    global _store
    if _store is None:
        url = os.getenv("DATABASE_URL", "").strip()
        if not url:
            raise TenantStoreError("DATABASE_URL is not set")
        _store = TenantStore(url)
    return _store


def reset_store() -> None:
    """Drop the cached store (tests, and Celery's per-task event loop)."""
    global _store
    _store = None


# --- module-level API -------------------------------------------------------

async def create_tenant(
    *,
    tenant_id: str,
    api_key: str,
    plan: str,
    email: str,
    status: str = STATUS_ACTIVE,
    expires_at: datetime | None = None,
    ls_customer_id: str | None = None,
) -> dict:
    """Insert a tenant row. Raises on a duplicate tenant_id or api_key."""
    if plan not in PLANS:
        raise ValueError(f"Unknown plan {plan!r}; expected one of {sorted(PLANS)}")
    return await get_store().create(
        tenant_id=tenant_id,
        api_key=api_key,
        plan=plan,
        email=email,
        status=status,
        expires_at=expires_at,
        ls_customer_id=ls_customer_id,
    )


async def get_tenant_by_api_key(api_key: str) -> dict | None:
    """Look up a tenant by its API key, or None."""
    if not api_key:
        return None
    return await get_store().get_by_api_key(api_key)


async def list_tenants() -> list[dict]:
    """Every tenant, oldest first."""
    return await get_store().list_all()


async def activate_tenant(customer_id: str) -> dict:
    """Grant access to the tenant behind ``customer_id``.

    Called from the Stripe webhook. Degrades to a log line when the database is
    unavailable: a billing webhook must not fail because Postgres is down.
    """
    updated = 0
    try:
        updated = await get_store().set_status_by_customer(customer_id, STATUS_ACTIVE)
    except Exception as exc:  # TenantStoreError, connection errors
        log.warning("tenant_activation_skipped", ls_customer_id=customer_id, error=str(exc))

    log.info("tenant_activated", ls_customer_id=customer_id, rows_updated=updated)
    return {"ok": True, "customer_id": customer_id, "status": "active", "rows_updated": updated}


async def deactivate_tenant(customer_id: str) -> dict:
    """Revoke access for the tenant behind ``customer_id``."""
    updated = 0
    try:
        updated = await get_store().set_status_by_customer(customer_id, STATUS_CANCELED)
    except Exception as exc:
        log.warning("tenant_deactivation_skipped", ls_customer_id=customer_id, error=str(exc))

    log.info("tenant_deactivated", ls_customer_id=customer_id, rows_updated=updated)
    return {
        "ok": True,
        "customer_id": customer_id,
        "status": "canceled",
        "rows_updated": updated,
    }
