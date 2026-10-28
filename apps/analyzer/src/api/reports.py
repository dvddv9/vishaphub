# -*- coding: utf-8 -*-
"""Markdown report files (v6.5).

One file per finished job, at ``DATA_DIR/reports/<job_id>.md`` — the same root
the pipeline already uses for ``result_*.json``, so a volume mount or a backup
covers both artefacts.

Saving is **fail-open**: a report that cannot be written must not fail the job
that produced it. The JSON result in the job store remains the source of truth;
the file is the downloadable copy.
"""
import re
from pathlib import Path

from src.config import DATA_DIR
from src.observability.logging import get_logger

log = get_logger(__name__)

REPORTS_SUBDIR = "reports"

#: Job ids are generated as ``job-<12 hex>``. Anything else is rejected before it
#: reaches the filesystem, so a crafted id cannot escape the reports directory.
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class InvalidReportPath(ValueError):
    """Raised when a job id is not safe to use as a file name."""


def reports_dir() -> Path:
    """Directory holding the Markdown reports."""
    return DATA_DIR / REPORTS_SUBDIR


def report_path(job_id: str) -> Path:
    """Path of the report for ``job_id``. Raises on a malformed id."""
    if not _JOB_ID_RE.match(job_id or "") or ".." in job_id:
        raise InvalidReportPath(f"unsafe job id: {job_id!r}")
    return reports_dir() / f"{job_id}.md"


def save_report(job_id: str, markdown: str | None) -> Path | None:
    """Write the report to disk. Returns the path, or None when it was skipped."""
    if not markdown:
        log.warning("report_save_skipped", job_id=job_id, reason="no markdown")
        return None

    try:
        path = report_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # write_bytes, not write_text: text mode rewrites "\n" to "\r\n" on
        # Windows, which would make the downloadable file differ byte-for-byte
        # from the markdown the API returns.
        path.write_bytes(markdown.encode("utf-8"))
    except Exception as exc:  # unsafe id, permissions, disk full
        log.warning("report_save_failed", job_id=job_id, error=str(exc))
        return None

    log.info("report_saved", job_id=job_id, chars=len(markdown), path=str(path))
    return path
