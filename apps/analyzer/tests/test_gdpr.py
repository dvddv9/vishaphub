# -*- coding: utf-8 -*-
"""GDPR export/erasure tests (v6.3) — stores are mocked, no database."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api import gdpr


def _jobs():
    return [
        {"job_id": "j1", "status": "done", "created_at": "2026-01-01T00:00:00+00:00"},
        {"job_id": "j2", "status": "failed", "created_at": "2026-01-02T00:00:00+00:00"},
    ]


@pytest.mark.asyncio
async def test_export_returns_jobs():
    with patch.object(gdpr, "list_jobs_async", AsyncMock(return_value=_jobs())), \
         patch.object(gdpr, "load_history", return_value=[{"filename": "a.py"}]):
        result = await gdpr.export_user_data("t1")

    assert result["tenant_id"] == "t1"
    assert [job["job_id"] for job in result["jobs"]] == ["j1", "j2"]
    assert result["history"] == [{"filename": "a.py"}]
    assert len(result["audit"]) == 2
    assert result["audit"][0]["job_id"] == "j1"
    assert "exported_at" in result


def test_export_requires_auth():
    from src.main import app

    client = TestClient(app)
    assert client.get("/api/me/data").status_code == 401


@pytest.mark.asyncio
async def test_delete_removes_data():
    with patch.object(gdpr, "list_jobs_async", AsyncMock(return_value=_jobs())), \
         patch.object(gdpr, "delete_job_async", AsyncMock(return_value=True)), \
         patch.object(gdpr, "clear_history", return_value=3):
        result = await gdpr.delete_user_data("t1")

    assert result["deleted"] == 2
    assert result["history_deleted"] == 3
    assert result["tenant_id"] == "t1"


def test_delete_requires_auth():
    from src.main import app

    client = TestClient(app)
    assert client.delete("/api/me").status_code == 401
