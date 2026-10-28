# -*- coding: utf-8 -*-
"""Celery app for Vishap (v6.5)."""
import os
from celery import Celery

def _get_celery_app() -> Celery:
    """Build a Celery app from the current environment.

    Exposed so tests can build an app from a patched environment without
    reloading the module. ``include`` registers the task module explicitly: the
    worker must import it to discover the tasks, and importing it only in the
    API process is not enough.
    """
    return Celery(
        "vishap",
        broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
        include=["src.api.tasks"],
    )


celery_app = _get_celery_app()

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)


def broker_available(timeout: float = 0.5) -> bool:
    """Quick TCP check: is the Redis broker reachable?"""
    import socket
    from urllib.parse import urlparse

    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    parsed = urlparse(broker_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379

    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (OSError, socket.error):
        return False
