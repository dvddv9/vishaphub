# -*- coding: utf-8 -*-
"""Audit-trail export for compliance reporting (v6.3, Block 17).

``GET /audit/export`` streams the jobs of the caller's tenant as CSV or JSON.
Rows come from ``list_jobs_async``, which already returns the legacy dict shape
(``status`` as a string, datetimes as ISO-8601 strings) and is tenant-scoped by
the caller's ``tenant_scope``.

The export deliberately drops the ``result`` payload: it is large, it is not
audit metadata, and SOC 2 / ISO 27001 reviews ask for *who did what when*, not
for the report bodies. The JSON projection therefore matches the CSV columns
rather than the full ``/status`` document.
"""
import csv
import io
from datetime import UTC, datetime
from typing import Any, Iterable, Literal

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse

from src.api.jobs import list_jobs_async

#: Column order is part of the export contract — append new fields at the end.
CSV_COLUMNS = [
    "job_id",
    "status",
    "filename",
    "tenant_id",
    "created_at",
    "started_at",
    "finished_at",
    "error",
]

VALID_STATUSES = {"queued", "running", "done", "failed"}
DEFAULT_LIMIT = 1000
MAX_LIMIT = 10000


def _parse_bound(value: str | None, name: str) -> datetime | None:
    """Parse an ISO-8601 query bound; naive values are treated as UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid {name} date: {value!r} (expected ISO 8601)"
        ) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _job_datetime(value: Any) -> datetime | None:
    """Normalise a job datetime (str or datetime) for comparison."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _status_value(job: dict) -> str:
    status = job.get("status")
    return getattr(status, "value", status) or ""


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return value or ""


def project(job: dict) -> dict:
    """Project a job record onto the audit columns (no ``result`` payload)."""
    return {
        "job_id": job.get("job_id", ""),
        "status": _status_value(job),
        "filename": job.get("filename", ""),
        "tenant_id": job.get("tenant_id") or "",
        "created_at": _iso(job.get("created_at")),
        "started_at": _iso(job.get("started_at")),
        "finished_at": _iso(job.get("finished_at")),
        "error": job.get("error") or "",
    }


def filter_jobs(
    jobs: Iterable[dict],
    *,
    status: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """Apply the audit filters. Inclusive on both bounds."""
    if status and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status {status!r}; expected one of {sorted(VALID_STATUSES)}",
        )
    start = _parse_bound(from_date, "from")
    end = _parse_bound(to_date, "to")

    selected: list[dict] = []
    for job in jobs:
        if status and _status_value(job) != status:
            continue
        created = _job_datetime(job.get("created_at"))
        if start is not None and (created is None or created < start):
            continue
        if end is not None and (created is None or created > end):
            continue
        selected.append(job)
    return selected


def _row_to_csv(row: dict) -> str:
    buffer = io.StringIO()
    csv.DictWriter(
        buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n"
    ).writerow(row)
    return buffer.getvalue()


def _csv_chunks(jobs: Iterable[dict]) -> Iterable[str]:
    header = io.StringIO()
    csv.DictWriter(
        header, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n"
    ).writeheader()
    yield header.getvalue()
    for job in jobs:
        yield _row_to_csv(project(job))


async def export_audit(
    format: Literal["csv", "json"] = "csv",
    from_date: str | None = None,
    to_date: str | None = None,
    status: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Response:
    """Build the audit export response for the current tenant."""
    if format not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="format must be 'csv' or 'json'")

    bounded = max(1, min(int(limit), MAX_LIMIT))
    jobs = await list_jobs_async(limit=bounded)
    selected = filter_jobs(jobs, status=status, from_date=from_date, to_date=to_date)

    if format == "json":
        return JSONResponse(
            [project(job) for job in selected],
            headers={"Content-Disposition": 'attachment; filename="audit.json"'},
        )

    return StreamingResponse(
        _csv_chunks(selected),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
    )
