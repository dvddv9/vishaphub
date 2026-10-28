# -*- coding: utf-8 -*-
"""Job store access layer (v6.3: async store, synchronous legacy facade).

The concrete stores are async (see ``src/api/job_store.py``). This module exposes
two surfaces:

* **async functions** (``*_async``) used by the FastAPI endpoints and Celery —
  these always ``await`` the store. Before v6.3 the PostgreSQL backend's
  coroutines were never awaited, so ``JOB_STORE=postgres`` crashed on the first
  ``create_job`` and Celery updates silently did nothing.
* a **synchronous facade** with the historical names (``create_job``,
  ``get_job``, ...) that drives the async functions through ``asyncio.run``.
  It is used by legacy module-level callers and the existing unit tests.

The synchronous facade must not be called from inside a running event loop —
use the ``*_async`` variant there.
"""
import asyncio
import os
from datetime import datetime
from typing import Any, Coroutine, TypeVar

from src.api.job_store import (
    DEFAULT_TENANT,
    Job,
    JobStatus,
    JobStore,
    get_tenant,
    set_tenant,
)
from src.api.job_store_memory import InMemoryJobStore

T = TypeVar("T")

_store: JobStore | None = None


def get_store() -> JobStore:
    global _store
    if _store is None:
        backend = os.getenv("JOB_STORE", "memory").lower()
        if backend == "memory":
            _store = InMemoryJobStore()
        elif backend == "postgres":
            from src.api.job_store_postgres import PostgresJobStore
            db_url = os.getenv("DATABASE_URL")
            if not db_url:
                raise ValueError("DATABASE_URL required for JOB_STORE=postgres")
            _store = PostgresJobStore(db_url)
        else:
            raise ValueError(f"Unknown JOB_STORE={backend!r}")
    return _store


def reset_store() -> None:
    """Drop the cached store.

    Needed by the Celery worker: each task runs ``asyncio.run`` on a fresh event
    loop, and a SQLAlchemy async engine is bound to the loop that created it.
    """
    global _store
    _store = None


def _run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Drive a coroutine from synchronous code."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    coro.close()
    raise RuntimeError(
        "The synchronous job-store facade cannot run inside an event loop. "
        "Use the *_async variant (create_job_async, get_job_async, ...) instead."
    )


def _effective_tenant(tenant_id: str | None) -> str:
    """Explicit tenant wins; otherwise the bound tenant; otherwise the default."""
    if tenant_id is not None:
        return tenant_id
    return get_tenant() or DEFAULT_TENANT


def _job_to_dict(job: Job) -> dict:
    """Convert Job to legacy dict shape (status as str, ISO datetimes)."""
    return {
        "job_id": job.job_id,
        "status": job.status.value,  # legacy: str, НЕ JobStatus
        "filename": job.filename,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "result": job.result,
        "error": job.error,
        "tenant_id": job.tenant_id,  # новое поле, не мешает
    }


def _normalise_update(kwargs: dict) -> dict:
    """Legacy coercion: status str -> JobStatus, ISO datetime str -> datetime."""
    if "status" in kwargs and isinstance(kwargs["status"], str):
        kwargs["status"] = JobStatus(kwargs["status"])
    for dt_field in ("started_at", "finished_at"):
        if dt_field in kwargs and isinstance(kwargs[dt_field], str):
            kwargs[dt_field] = datetime.fromisoformat(kwargs[dt_field])
    return kwargs


# --- async API (endpoints, Celery) -----------------------------------------

async def create_job_async(filename: str = "unknown", tenant_id: str | None = None) -> str:
    job = await get_store().create(filename=filename, tenant_id=_effective_tenant(tenant_id))
    return job.job_id


async def get_job_async(job_id: str) -> dict | None:
    job = await get_store().get(job_id)
    return _job_to_dict(job) if job else None


async def update_job_async(job_id: str, **kwargs) -> bool:
    updated = await get_store().update(job_id, **_normalise_update(kwargs))
    return updated is not None


async def delete_job_async(job_id: str) -> bool:
    return await get_store().delete(job_id)


async def list_jobs_async(limit: int = 50) -> list[dict]:
    return [_job_to_dict(j) for j in await get_store().list_jobs(limit=limit)]


async def clear_jobs_async() -> int:
    return await get_store().clear()


async def job_count_async() -> int:
    return await get_store().count()


# --- synchronous legacy facade ---------------------------------------------

def create_job(filename: str = "unknown", tenant_id: str | None = None) -> str:
    return _run_sync(create_job_async(filename, tenant_id))


def get_job(job_id: str) -> dict | None:
    return _run_sync(get_job_async(job_id))


def update_job(job_id: str, **kwargs) -> bool:
    return _run_sync(update_job_async(job_id, **kwargs))


def delete_job(job_id: str) -> bool:
    return _run_sync(delete_job_async(job_id))


def list_jobs(limit: int = 50) -> list[dict]:
    return _run_sync(list_jobs_async(limit=limit))


def clear_jobs() -> int:
    return _run_sync(clear_jobs_async())


def job_count() -> int:
    return _run_sync(job_count_async())


# --- Tenant context (v6.3 RLS) ---

def set_current_tenant(tenant_id: str | None) -> None:
    """Bind the tenant for the current request/task (see job_store.tenant_scope)."""
    set_tenant(tenant_id)


def get_current_tenant() -> str | None:
    """Return the tenant bound to the current request/task."""
    return get_tenant()
