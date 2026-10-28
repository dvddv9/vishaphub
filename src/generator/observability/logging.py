"""Logging for the server and the pipeline, standard library only.

The analog of Vishap's `observability/logging.py` (which uses structlog): `setup_logging`, `get_logger`, and ids
bound to the current context (`bind_run_id`, `bind_request_id`) that appear in every line written while they
are bound. Pretty text by default, JSON with LOG_FORMAT=json; level from LOG_LEVEL (default WARNING, so the
command line stays quiet unless asked).

Whatever is logged passes a filter that removes the model key, so a key cannot reach a log even by accident.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextvars import ContextVar

_run_id: ContextVar[str | None] = ContextVar("run_id", default=None)
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
ROOT = "generator"
logging.getLogger(ROOT).addHandler(logging.NullHandler())     # a library is silent until setup_logging()


class _KeyFilter(logging.Filter):
    """Replace the configured model key (and anything key-shaped) in every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        from generator.tools.redact import redact
        msg = record.getMessage()
        key = os.environ.get("CUSTOM_LLM_KEY", "")
        if key and key in msg:
            msg = msg.replace(key, "[key]")
        record.msg, record.args = redact(msg).text, ()
        return True


class _Formatter(logging.Formatter):
    def __init__(self, fmt: str):
        super().__init__()
        self.fmt = fmt

    def format(self, record: logging.LogRecord) -> str:
        ctx = {k: v for k, v in (("run_id", _run_id.get()), ("request_id", _request_id.get())) if v}
        ctx.update(getattr(record, "fields", {}) or {})
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z"
        if self.fmt == "json":
            data = {"time": stamp, "level": record.levelname.lower(), "logger": record.name,
                    "message": record.getMessage(), **ctx}
            if record.exc_info:
                data["exception"] = self.formatException(record.exc_info)
            return json.dumps(data, ensure_ascii=False)
        extra = " ".join(f"{k}={v}" for k, v in ctx.items())
        line = f"{stamp} {record.levelname:<7} {record.name}: {record.getMessage()}" + (f"  [{extra}]" if extra else "")
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logging(level: str | None = None, fmt: str | None = None, stream=None) -> None:
    """Configure the `generator` logger. Call once at startup; calling again replaces the handler."""
    level = (level or os.getenv("LOG_LEVEL", "WARNING")).upper()
    fmt = (fmt or os.getenv("LOG_FORMAT", "pretty")).lower()
    logger = logging.getLogger(ROOT)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(_Formatter(fmt))
    handler.addFilter(_KeyFilter())
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level, logging.WARNING))
    logger.propagate = False


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(f"{ROOT}.{name}" if name else ROOT)


def bind_run_id(run_id: str) -> None:
    _run_id.set(run_id)


def bind_request_id(request_id: str) -> None:
    _request_id.set(request_id)


def clear_context() -> None:
    _run_id.set(None)
    _request_id.set(None)
