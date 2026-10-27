# -*- coding: utf-8 -*-
"""Tests for async API (v6.0): job store + endpoints.

Job store: src/api/jobs.py
Endpoints: POST /analyze/async, GET /status/{job_id}, GET /report/{job_id}
"""
import pytest
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from src.config import CONVEYOR_API_KEY as _KEY

_AUTH = {"X-API-Key": _KEY} if _KEY else {}

from src.api.jobs import (
    create_job, get_job, update_job, delete_job, list_jobs, clear_jobs, job_count,
)


@pytest.fixture(autouse=True)
def _clean_jobs():
    clear_jobs()
    yield
    clear_jobs()


# ============================================================
# Job store -- unit tests
# ============================================================

def test_create_job_returns_id():
    jid = create_job("test.py")
    assert jid.startswith("job-")
    assert len(jid) == 16


def test_create_job_initial_status():
    jid = create_job("test.py")
    job = get_job(jid)
    assert job is not None
    assert job["status"] == "queued"
    assert job["filename"] == "test.py"
    assert job["result"] is None
    assert job["error"] is None
    assert job["created_at"] is not None


def test_get_missing_job_returns_none():
    assert get_job("job-nonexistent") is None


def test_update_job_status():
    jid = create_job("test.py")
    ok = update_job(jid, status="running")
    assert ok is True
    assert get_job(jid)["status"] == "running"


def test_update_missing_job_returns_false():
    ok = update_job("job-nonexistent", status="running")
    assert ok is False


def test_delete_job():
    jid = create_job("test.py")
    assert delete_job(jid) is True
    assert get_job(jid) is None
    assert delete_job(jid) is False


def test_list_jobs_empty():
    assert list_jobs() == []


def test_list_jobs_returns_all():
    a = create_job("a.py")
    b = create_job("b.py")
    items = list_jobs()
    assert len(items) == 2
    ids = [j["job_id"] for j in items]
    assert a in ids
    assert b in ids


def test_list_jobs_limit():
    for i in range(5):
        create_job(f"f{i}.py")
    items = list_jobs(limit=3)
    assert len(items) == 3


def test_job_count():
    assert job_count() == 0
    create_job("a.py")
    create_job("b.py")
    assert job_count() == 2


def test_clear_jobs():
    create_job("a.py")
    create_job("b.py")
    n = clear_jobs()
    assert n == 2
    assert job_count() == 0


def test_get_job_returns_copy():
    jid = create_job("test.py")
    job1 = get_job(jid)
    job1["status"] = "HACKED"
    job2 = get_job(jid)
    assert job2["status"] == "queued"


# ============================================================
# Endpoints -- integration tests
# ============================================================

@pytest.fixture
def client():
    from src.main import app
    return TestClient(app)


def test_analyze_async_creates_job(client):
    from src.config import CONVEYOR_API_KEY
    headers = {"X-API-Key": CONVEYOR_API_KEY} if CONVEYOR_API_KEY else {}
    with patch("src.main._run_job_async", new_callable=AsyncMock):
        r = client.post(
            "/analyze/async",
            json={"material": "def f(): pass", "filename": "test.py"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["job_id"].startswith("job-")


def test_status_returns_job_info(client):
    jid = create_job("test.py")
    r = client.get(f"/status/{jid}", headers=_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["job_id"] == jid
    assert data["status"] == "queued"


def test_status_404_for_missing_job(client):
    r = client.get("/status/job-nonexistent", headers=_AUTH)
    assert r.status_code == 404


def test_report_409_when_not_done(client):
    jid = create_job("test.py")
    update_job(jid, status="running")
    r = client.get(f"/report/{jid}", headers=_AUTH)
    assert r.status_code == 409


def test_report_returns_result_when_done(client):
    jid = create_job("test.py")
    update_job(jid, status="done", result={"ok": True, "audit_id": "abc"})
    r = client.get(f"/report/{jid}", headers=_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["audit_id"] == "abc"


def test_report_404_for_missing_job(client):
    r = client.get("/report/job-nonexistent", headers=_AUTH)
    assert r.status_code == 404


def test_report_409_when_failed(client):
    jid = create_job("test.py")
    update_job(jid, status="failed", error="boom")
    r = client.get(f"/report/{jid}", headers=_AUTH)
    assert r.status_code == 409


def test_job_lifecycle_done(client):
    jid = create_job("test.py")
    update_job(jid, status="running")
    update_job(jid, status="done", result={"ok": True})
    status_r = client.get(f"/status/{jid}", headers=_AUTH)
    assert status_r.json()["status"] == "done"
    report_r = client.get(f"/report/{jid}", headers=_AUTH)
    assert report_r.status_code == 200
