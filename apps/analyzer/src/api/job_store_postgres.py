# -*- coding: utf-8 -*-
"""PostgreSQL JobStore implementation (v6.1) via SQLAlchemy 2.0 async.

Multi-tenant isolation (v6.3) is delegated to PostgreSQL row-level security:
every session opened by the store first applies
``set_config('app.current_tenant', <tenant>, true)``, so the policy installed by
alembic revision ``002_add_rls_jobs`` filters every SELECT/UPDATE/DELETE.
"""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, UTC
from typing import AsyncIterator

from sqlalchemy import DateTime, Index, String, Text, delete, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.api.job_store import Job, JobStatus, get_tenant, set_tenant
from src.observability.logging import get_logger
from src.observability.metrics import observe_job_created, observe_job_finished

log = get_logger(__name__)

#: Parameterised; ``SET LOCAL app.current_tenant = :x`` is not valid PostgreSQL,
#: and ``is_local = true`` scopes the value to the current transaction.
_SET_TENANT_SQL = text("SELECT set_config('app.current_tenant', :tenant, true)")


class Base(DeclarativeBase):
    """Declarative base for SQLAlchemy models."""


class JobModel(Base):
    """SQLAlchemy model mapping to the ``jobs`` table."""

    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_jobs_tenant_created", "tenant_id", "created_at"),
    )


class PostgresJobStore:
    """Async PostgreSQL-backed JobStore (SQLAlchemy 2.0 async).

    Note: methods are async (unlike the sync InMemoryJobStore); the sync shim
    in src/api/jobs.py keeps a sync facade for the legacy module-level API.
    """

    def __init__(self, database_url: str) -> None:
        self._engine = create_async_engine(database_url)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    # --- tenant context -----------------------------------------------------

    def set_tenant(self, tenant_id: str | None) -> None:
        """Bind the tenant for subsequent sessions opened by this store."""
        set_tenant(tenant_id)

    def get_tenant(self) -> str | None:
        """Return the currently bound tenant."""
        return get_tenant()

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        """Open a session and apply the tenant context inside its transaction."""
        async with self._session_factory() as session:
            tenant = get_tenant()
            if tenant:
                # Runs inside the autobegun transaction, so `is_local=true`
                # keeps the value for exactly this session's work.
                await session.execute(_SET_TENANT_SQL, {"tenant": tenant})
            yield session

    @staticmethod
    def _to_job(model: "JobModel") -> Job:
        return Job(
            job_id=model.job_id,
            status=JobStatus(model.status),
            created_at=model.created_at,
            updated_at=model.updated_at,
            filename=model.filename,
            tenant_id=model.tenant_id,
            result=model.result,
            error=model.error,
            started_at=model.started_at,
            finished_at=model.finished_at,
        )

    async def create(self, filename: str = "unknown", *,
                     tenant_id: str | None = None) -> Job:
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        model = JobModel(
            job_id=job_id,
            status=JobStatus.QUEUED.value,
            filename=filename,
            created_at=now,
            updated_at=now,
            tenant_id=tenant_id if tenant_id is not None else get_tenant(),
            result=None,
            error=None,
            started_at=None,
            finished_at=None,
        )
        async with self._session() as session:
            session.add(model)
            await session.commit()
        log.info("job_created", job_id=job_id, filename=filename, backend="postgres")
        observe_job_created(JobStatus.QUEUED.value)
        return self._to_job(model)

    async def get(self, job_id: str) -> Job | None:
        async with self._session() as session:
            model = await session.get(JobModel, job_id)
        return self._to_job(model) if model else None

    async def update(self, job_id: str, **kwargs) -> Job | None:
        # Defensive: accept JobStatus enums and ISO-string datetimes.
        if "status" in kwargs and isinstance(kwargs["status"], JobStatus):
            kwargs["status"] = kwargs["status"].value
        for dt_field in ("started_at", "finished_at"):
            if dt_field in kwargs and isinstance(kwargs[dt_field], str):
                kwargs[dt_field] = datetime.fromisoformat(kwargs[dt_field])
        async with self._session() as session:
            model = await session.get(JobModel, job_id)
            if model is None:
                return None
            old_status = model.status
            for field, value in kwargs.items():
                setattr(model, field, value)
            model.updated_at = datetime.now(UTC)
            await session.commit()
        job = self._to_job(model)
        log.info("job_updated", job_id=job_id, status=job.status.value, backend="postgres")
        if job.status.value in ("done", "failed") and old_status != job.status.value:
            duration = 0.0
            if job.started_at and job.finished_at:
                duration = (job.finished_at - job.started_at).total_seconds()
            observe_job_finished(job.status.value, duration)
        return job

    async def delete(self, job_id: str) -> bool:
        async with self._session() as session:
            model = await session.get(JobModel, job_id)
            if model is None:
                return False
            await session.delete(model)
            await session.commit()
        log.info("job_deleted", job_id=job_id, backend="postgres")
        return True

    async def list_jobs(self, limit: int = 50) -> list[Job]:
        async with self._session() as session:
            result = await session.execute(
                select(JobModel).order_by(JobModel.created_at.desc()).limit(limit)
            )
            models = result.scalars().all()
        return [self._to_job(m) for m in models]

    async def clear(self) -> int:
        async with self._session() as session:
            result = await session.execute(delete(JobModel))
            await session.commit()
        return result.rowcount or 0

    async def count(self) -> int:
        async with self._session() as session:
            result = await session.execute(select(func.count()).select_from(JobModel))
            value = result.scalar()
        return value or 0
