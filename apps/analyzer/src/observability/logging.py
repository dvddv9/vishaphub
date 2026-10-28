# -*- coding: utf-8 -*-
"""structlog configuration (v6.1).

Pretty output in dev, JSON in prod. Exposes helpers for request/job-scoped
context via contextvars, so concurrent async requests never leak each other's
``job_id`` / ``request_id``.
"""
import logging
import os
import sys
from contextvars import ContextVar

import structlog

# Context vars for request/job-scoped data
_job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def setup_logging(level: str | None = None, fmt: str | None = None) -> None:
    """Configure structlog. Call once at app startup.

    ``level``: one of DEBUG/INFO/WARNING/ERROR/CRITICAL (default from
    ``LOG_LEVEL`` env var, else ``INFO``).
    ``fmt``: ``pretty`` (default) or ``json``.
    """
    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    fmt = (fmt or os.getenv("LOG_FORMAT", "pretty")).lower()

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    )


def get_logger(name: str | None = None):
    """Get a bound structlog logger."""
    return structlog.get_logger(name) if name else structlog.get_logger()


def bind_job_id(job_id: str) -> None:
    """Bind ``job_id`` to the current context for all subsequent logs."""
    _job_id_var.set(job_id)
    structlog.contextvars.bind_contextvars(job_id=job_id)


def bind_request_id(request_id: str) -> None:
    """Bind ``request_id`` to the current context for all subsequent logs."""
    _request_id_var.set(request_id)
    structlog.contextvars.bind_contextvars(request_id=request_id)


def clear_context() -> None:
    """Clear request/job-scoped contextvars."""
    _job_id_var.set(None)
    _request_id_var.set(None)
    structlog.contextvars.clear_contextvars()
