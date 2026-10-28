# -*- coding: utf-8 -*-
"""Audit-trail export tests (v6.3, Block 17) — no database required."""
import csv
import io
import json

import pytest
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from src.api import audit as audit_mod

# Mirrors the dict shape returned by src.api.jobs.list_jobs_async.
def _job(
    job_id: str = "job-1",
    status: str = "done",
    filename: str = "a.py",
    created_at: str = "2026-01-10T12:00:00+00:00",
    tenant_id: str = "t1",
    error: str | None = None,
) -> dict:
    return {
        "job_id": job_id,
        "status": status,
        "filename": filename,
        "created_at": created_at,
        "started_at": "2026-01-10T12:00:01+00:00",
        "finished_at": "2026-01-10T12:00:05+00:00",
        "result": {"final_markdown": "# report"},  # must NOT leak into the export
        "error": error,
        "tenant_id": tenant_id,
    }


def _patch_jobs(monkeypatch, jobs: list[dict]) -> None:
    async def fake_list(limit: int = 50) -> list[dict]:
        return jobs

    monkeypatch.setattr(audit_mod, "list_jobs_async", fake_list)


async def _body(response) -> str:
    """Read a StreamingResponse or a plain Response into text."""
    if isinstance(response, StreamingResponse):
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
        return b"".join(chunks).decode("utf-8")
    return response.body.decode("utf-8")


@pytest.mark.asyncio
async def test_export_csv(monkeypatch):
    _patch_jobs(monkeypatch, [_job()])

    response = await audit_mod.export_audit(format="csv")
    rows = list(csv.reader(io.StringIO(await _body(response))))

    assert rows[0] == audit_mod.CSV_COLUMNS
    assert len(rows) == 2  # header + one job
    assert rows[1][0] == "job-1"
    assert "audit.csv" in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_export_json(monkeypatch):
    _patch_jobs(monkeypatch, [_job()])

    response = await audit_mod.export_audit(format="json")
    payload = json.loads(await _body(response))

    assert isinstance(payload, list) and len(payload) == 1
    assert set(payload[0]) == set(audit_mod.CSV_COLUMNS)
    assert payload[0]["job_id"] == "job-1"
    assert payload[0]["status"] == "done"
    assert "result" not in payload[0]


@pytest.mark.asyncio
async def test_export_filter_status(monkeypatch):
    _patch_jobs(
        monkeypatch,
        [_job(job_id="job-done", status="done"), _job(job_id="job-failed", status="failed")],
    )

    response = await audit_mod.export_audit(format="json", status="done")
    payload = json.loads(await _body(response))

    assert [row["job_id"] for row in payload] == ["job-done"]


@pytest.mark.asyncio
async def test_export_filter_date(monkeypatch):
    _patch_jobs(
        monkeypatch,
        [
            _job(job_id="job-old", created_at="2026-01-01T00:00:00+00:00"),
            _job(job_id="job-new", created_at="2026-06-01T00:00:00+00:00"),
        ],
    )

    response = await audit_mod.export_audit(format="json", from_date="2026-03-01")
    payload = json.loads(await _body(response))

    assert [row["job_id"] for row in payload] == ["job-new"]


def test_export_tenant_isolation():
    """The endpoint only exports the caller's tenant, through tenant_scope."""
    from src.api import auth as auth_mod
    from src.api.jobs import create_job
    from src.auth.middleware import current_tenant
    from src.main import app

    tenant_a, tenant_b = "audit-tenant-a", "audit-tenant-b"
    create_job("a.py", tenant_id=tenant_a)
    create_job("b.py", tenant_id=tenant_b)

    headers = {"X-API-Key": auth_mod.API_KEY} if auth_mod.API_KEY else {}
    client = TestClient(app)
    app.dependency_overrides[current_tenant] = lambda: tenant_a
    try:
        response = client.get("/audit/export?format=json", headers=headers)
    finally:
        app.dependency_overrides.pop(current_tenant, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload, "expected at least one exported job"
    assert {row["tenant_id"] for row in payload} == {tenant_a}
