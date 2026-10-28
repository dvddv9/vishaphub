# -*- coding: utf-8 -*-
"""GDPR self-service export and erasure (v6.3).

Both functions operate on a **tenant**, not on a Clerk user id: jobs are
partitioned by ``tenant_id`` (and protected by row-level security), while
``tenant_id`` equals ``org_id`` for organisation members and the user id for
personal accounts. Callers must bind the tenant first (``tenant_scope``).
"""
from datetime import UTC, datetime

from src.api.jobs import delete_job_async, list_jobs_async
from src.storage.history import clear_history, load_history

#: Jobs are capped by the store; a GDPR export should not silently truncate at 50.
EXPORT_JOB_LIMIT = 10000


async def export_user_data(tenant_id: str) -> dict:
    """Return everything stored for one tenant: jobs, history and audit slice."""
    jobs = await list_jobs_async(limit=EXPORT_JOB_LIMIT)
    history = load_history(tenant_id=tenant_id)
    audit = [
        {
            "job_id": job.get("job_id"),
            "status": job.get("status"),
            "created_at": job.get("created_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "error": job.get("error"),
        }
        for job in jobs
    ]
    return {
        "tenant_id": tenant_id,
        "exported_at": datetime.now(UTC).isoformat(),
        "jobs": jobs,
        "history": history,
        "audit": audit,
    }


async def delete_user_data(tenant_id: str) -> dict:
    """Erase every job and history entry belonging to one tenant."""
    jobs = await list_jobs_async(limit=EXPORT_JOB_LIMIT)
    deleted = 0
    for job in jobs:
        job_id = job.get("job_id")
        if job_id and await delete_job_async(job_id):
            deleted += 1

    history_deleted = clear_history(tenant_id=tenant_id)
    return {
        "tenant_id": tenant_id,
        "deleted": deleted,
        "history_deleted": history_deleted,
    }
