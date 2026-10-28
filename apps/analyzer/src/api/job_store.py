# -*- coding: utf-8 -*-
"""JobStore contract for async analysis (v6.0.3, tenant-aware in v6.3).

Defines the Job dataclass, JobStatus enum, the JobStore Protocol, and the
per-request tenant context used for multi-tenant isolation (RLS).
"""
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterator, Protocol

# Tenant used when a request carries no Clerk identity (legacy X-API-Key access).
# Must match the rows backfilled in alembic revision 002_add_rls_jobs.
DEFAULT_TENANT = os.getenv("VISHAP_DEFAULT_TENANT", "public")

_current_tenant: ContextVar[str | None] = ContextVar("vishap_current_tenant", default=None)


def set_tenant(tenant_id: str | None) -> None:
    """Bind the tenant to the current async task (no database round-trip).

    ``SET LOCAL`` cannot be used here: it is transaction-scoped, so a value set
    on one connection is gone as soon as that transaction ends. The value is
    stored in a context variable instead and applied with
    ``set_config('app.current_tenant', ..., true)`` by every session that the
    PostgreSQL store opens (see ``PostgresJobStore._session``).
    """
    _current_tenant.set(tenant_id)


def get_tenant() -> str | None:
    """Return the tenant bound to the current async task, if any."""
    return _current_tenant.get()


@contextmanager
def tenant_scope(tenant_id: str | None) -> Iterator[str | None]:
    """Bind ``tenant_id`` for the duration of the block, then restore."""
    token = _current_tenant.set(tenant_id)
    try:
        yield tenant_id
    finally:
        _current_tenant.reset(token)


class JobStatus(str, Enum):
    """Job lifecycle statuses. Values match legacy dict statuses."""
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class Job:
    """Immutable job record."""
    job_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    filename: str
    tenant_id: str | None = None
    result: dict | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobStore(Protocol):
    """Storage contract for async analysis jobs (v6.3: fully async).

    Both implementations are async so the PostgreSQL backend's coroutines are
    always awaited. The synchronous legacy facade lives in src/api/jobs.py.
    """

    async def create(self, filename: str = "unknown", *,
                     tenant_id: str | None = None) -> Job: ...

    async def get(self, job_id: str) -> Job | None: ...

    async def update(self, job_id: str, **kwargs) -> Job | None: ...

    async def delete(self, job_id: str) -> bool: ...

    async def list_jobs(self, limit: int = 50) -> list[Job]: ...

    async def clear(self) -> int: ...

    async def count(self) -> int: ...

    def set_tenant(self, tenant_id: str | None) -> None: ...

    def get_tenant(self) -> str | None: ...
