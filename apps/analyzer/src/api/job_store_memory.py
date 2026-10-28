# -*- coding: utf-8 -*-
"""In-memory JobStore implementation (v6.0.3, async since v6.3, tenant-aware)."""
import uuid
from dataclasses import replace
from datetime import datetime, UTC
from threading import RLock

from src.api.job_store import Job, JobStatus, get_tenant, set_tenant
from src.observability.logging import get_logger
from src.observability.metrics import observe_job_created, observe_job_finished

log = get_logger(__name__)


class InMemoryJobStore:
    """Thread-safe in-memory job store with optional tenant scoping.

    Methods are ``async`` to satisfy the :class:`~src.api.job_store.JobStore`
    contract shared with the PostgreSQL backend, even though no I/O is involved.

    Tenant scoping mirrors the PostgreSQL RLS policy: when a tenant is bound
    (``set_tenant``), reads and writes only see rows belonging to it. With no
    tenant bound the store behaves as before (single-tenant dev mode).
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = RLock()

    # --- tenant context -----------------------------------------------------

    def set_tenant(self, tenant_id: str | None) -> None:
        set_tenant(tenant_id)

    def get_tenant(self) -> str | None:
        return get_tenant()

    @staticmethod
    def _visible(job: Job, tenant: str | None) -> bool:
        """RLS equivalent: NULL tenant rows are only visible without a tenant."""
        if tenant is None:
            return True
        return job.tenant_id == tenant

    # --- CRUD ---------------------------------------------------------------

    async def create(self, filename: str = "unknown", *,
                     tenant_id: str | None = None) -> Job:
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        job = Job(
            job_id=job_id,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            filename=filename,
            tenant_id=tenant_id if tenant_id is not None else get_tenant(),
        )
        with self._lock:
            self._jobs[job_id] = job
        log.info("job_created", job_id=job_id, filename=filename, backend="memory")
        observe_job_created(job.status.value)
        return job

    async def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None and not self._visible(job, get_tenant()):
            return None
        return job

    async def update(self, job_id: str, **kwargs) -> Job | None:
        with self._lock:
            old = self._jobs.get(job_id)
            if old is None or not self._visible(old, get_tenant()):
                return None
            new = replace(old, updated_at=datetime.now(UTC), **kwargs)
            self._jobs[job_id] = new
            _status = new.status.value if isinstance(new.status, JobStatus) else new.status
            log.info("job_updated", job_id=job_id, status=_status, backend="memory")
            _old_status = old.status.value if isinstance(old.status, JobStatus) else old.status
            if _status in ("done", "failed") and _old_status != _status:
                duration = 0.0
                if new.started_at and new.finished_at:
                    duration = (new.finished_at - new.started_at).total_seconds()
                observe_job_finished(_status, duration)
            return new

    async def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not self._visible(job, get_tenant()):
                return False
            del self._jobs[job_id]
            log.info("job_deleted", job_id=job_id, backend="memory")
            return True

    async def list_jobs(self, limit: int = 50) -> list[Job]:
        tenant = get_tenant()
        with self._lock:
            items = [j for j in self._jobs.values() if self._visible(j, tenant)]
        return items[-limit:]

    async def clear(self) -> int:
        tenant = get_tenant()
        with self._lock:
            if tenant is None:
                n = len(self._jobs)
                self._jobs.clear()
                return n
            doomed = [jid for jid, j in self._jobs.items() if self._visible(j, tenant)]
            for jid in doomed:
                del self._jobs[jid]
            return len(doomed)

    async def count(self) -> int:
        tenant = get_tenant()
        with self._lock:
            return sum(1 for j in self._jobs.values() if self._visible(j, tenant))
