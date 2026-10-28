# -*- coding: utf-8 -*-
"""Unit tests for PostgresJobStore (mocked async session — no live Postgres)."""
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.job_store import Job, JobStatus
from src.api.job_store_postgres import JobModel, PostgresJobStore


def _model(**overrides) -> JobModel:
    now = datetime.now(UTC)
    data = dict(
        job_id="job-abc123def456",
        status="queued",
        filename="x.py",
        created_at=now,
        updated_at=now,
        started_at=None,
        finished_at=None,
        tenant_id=None,
        result=None,
        error=None,
    )
    data.update(overrides)
    return JobModel(**data)


@pytest.fixture
def session():
    s = MagicMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.get = AsyncMock()
    s.execute = AsyncMock()
    s.delete = AsyncMock()
    return s


@pytest.fixture
def store(session):
    factory = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx
    with patch("src.api.job_store_postgres.create_async_engine", return_value=MagicMock()), \
         patch("src.api.job_store_postgres.async_sessionmaker", return_value=factory):
        return PostgresJobStore("postgresql+asyncpg://u:p@localhost/db")


# --- Protocol shape ---

def test_implements_protocol_methods():
    for name in ("create", "get", "update", "delete", "list_jobs", "clear", "count"):
        assert hasattr(PostgresJobStore, name), name


# --- create ---

@pytest.mark.asyncio
async def test_create_returns_job(store, session):
    job = await store.create("x.py")
    assert isinstance(job, Job)
    assert job.job_id.startswith("job-")
    assert len(job.job_id) == 16
    assert job.status is JobStatus.QUEUED
    assert job.filename == "x.py"
    assert job.tenant_id is None
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_with_tenant_id(store):
    job = await store.create("x.py", tenant_id="t1")
    assert job.tenant_id == "t1"


# --- get ---

@pytest.mark.asyncio
async def test_get_returns_job(store, session):
    session.get.return_value = _model(status="running")
    job = await store.get("job-abc123def456")
    assert isinstance(job, Job)
    assert job.job_id == "job-abc123def456"
    assert job.status is JobStatus.RUNNING


@pytest.mark.asyncio
async def test_get_missing_returns_none(store, session):
    session.get.return_value = None
    assert await store.get("nope") is None


# --- update ---

@pytest.mark.asyncio
async def test_update_returns_job(store, session):
    session.get.return_value = _model()
    job = await store.update("job-abc123def456", status=JobStatus.RUNNING)
    assert isinstance(job, Job)
    assert job.status is JobStatus.RUNNING


@pytest.mark.asyncio
async def test_update_bumps_updated_at(store, session):
    model = _model()
    old = model.updated_at
    session.get.return_value = model
    job = await store.update("job-abc123def456", status=JobStatus.RUNNING)
    assert job.updated_at >= old


@pytest.mark.asyncio
async def test_update_converts_started_at_iso(store, session):
    session.get.return_value = _model()
    iso = "2026-01-15T10:00:00+00:00"
    job = await store.update("job-abc123def456", started_at=iso)
    assert isinstance(job.started_at, datetime)
    assert job.started_at == datetime.fromisoformat(iso)


@pytest.mark.asyncio
async def test_update_converts_finished_at_iso(store, session):
    session.get.return_value = _model()
    iso = "2026-01-15T10:00:00+00:00"
    job = await store.update("job-abc123def456", finished_at=iso)
    assert isinstance(job.finished_at, datetime)
    assert job.finished_at == datetime.fromisoformat(iso)


@pytest.mark.asyncio
async def test_update_missing_returns_none(store, session):
    session.get.return_value = None
    assert await store.update("nope", status=JobStatus.RUNNING) is None


# --- delete ---

@pytest.mark.asyncio
async def test_delete_returns_true(store, session):
    session.get.return_value = _model()
    assert await store.delete("job-abc123def456") is True
    session.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_missing_returns_false(store, session):
    session.get.return_value = None
    assert await store.delete("nope") is False


# --- list / clear / count ---

@pytest.mark.asyncio
async def test_list_jobs_returns_jobs(store, session):
    result = MagicMock()
    result.scalars.return_value.all.return_value = [
        _model(job_id="job-1"),
        _model(job_id="job-2"),
    ]
    session.execute.return_value = result
    jobs = await store.list_jobs()
    assert [j.job_id for j in jobs] == ["job-1", "job-2"]
    assert all(isinstance(j, Job) for j in jobs)


@pytest.mark.asyncio
async def test_list_jobs_limit(store, session):
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    await store.list_jobs(limit=7)
    stmt = session.execute.call_args.args[0]
    assert "LIMIT" in str(stmt).upper()


@pytest.mark.asyncio
async def test_clear_returns_int(store, session):
    result = MagicMock()
    result.rowcount = 3
    session.execute.return_value = result
    assert await store.clear() == 3


@pytest.mark.asyncio
async def test_count_returns_int(store, session):
    result = MagicMock()
    result.scalar.return_value = 5
    session.execute.return_value = result
    assert await store.count() == 5


# --- tenant context (v6.3 RLS) ---

def test_store_exposes_tenant_methods(store):
    assert hasattr(store, "set_tenant")
    assert hasattr(store, "get_tenant")


@pytest.mark.asyncio
async def test_set_tenant_applies_guc(store, session):
    from src.api.job_store import set_tenant

    set_tenant(None)
    store.set_tenant("t1")
    assert store.get_tenant() == "t1"

    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    await store.list_jobs()

    first = session.execute.await_args_list[0]
    assert "set_config" in str(first.args[0])
    assert first.args[1] == {"tenant": "t1"}

    store.set_tenant(None)
    assert store.get_tenant() is None
