# -*- coding: utf-8 -*-
"""Celery tasks (v6.1 queue, async job store since v6.3).

`run_analysis_task` replaces the in-process BackgroundTasks path: the API
enqueues the job, a separate Celery worker executes the pipeline and updates
the JobStore (memory or postgres).

Celery tasks are synchronous, so the store work is driven through a single
`asyncio.run` per task. The store is reset first because a SQLAlchemy async
engine is bound to the event loop that created it, and every task gets a new one.
"""
import asyncio
import inspect
import os

from src.api.celery_app import celery_app
from src.api.job_store import tenant_scope
from src.api.jobs import get_store, reset_store
from src.api.reports import save_report
from src.api.webhooks import notify_webhook
from src.observability.tracing import span
from src.pipeline.orchestrator import run_pipeline


async def _maybe_await(value):
    """Await the store call when it is awaitable.

    The real stores are async since v6.3, but tests replace ``get_store`` with a
    plain ``MagicMock`` whose methods are synchronous. This keeps both working.
    """
    if inspect.isawaitable(value):
        return await value
    return value


async def _execute(job_id: str, material: str, filename: str,
                   tenant_id: str | None) -> None:
    """Run one job inside the task's event loop."""
    if os.getenv("JOB_STORE", "memory").lower() == "postgres":
        # Engine pools are loop-bound; this task owns a brand-new loop.
        reset_store()

    with tenant_scope(tenant_id):
        store = get_store()
        try:
            await _maybe_await(store.update(job_id, status="running"))
            result = run_pipeline(material, filename)
            await _maybe_await(store.update(job_id, status="done", result=result))
            # Downloadable copy; fail-open so a disk problem cannot fail the job.
            save_report(job_id, (result or {}).get("final_markdown"))
            await notify_webhook(
                "job.completed", {"job_id": job_id, "tenant_id": tenant_id, "status": "done"}
            )
        except Exception as exc:
            await _maybe_await(store.update(job_id, status="failed", error=str(exc)))
            await notify_webhook(
                "job.failed",
                {
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "status": "failed",
                    "error": str(exc),
                },
            )
            raise


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def run_analysis_task(self, job_id: str, material: str, filename: str,
                      tenant_id: str | None = None):
    """Run the analysis pipeline for a queued job (Celery worker task)."""
    with span("celery.run_analysis", job_id=job_id):  # filename removed: PII risk in Tempo
        try:
            asyncio.run(_execute(job_id, material, filename, tenant_id))
            return job_id
        except Exception as exc:
            raise self.retry(exc=exc)
