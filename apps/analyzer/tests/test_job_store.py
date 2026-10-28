# -*- coding: utf-8 -*-
"""Tests for the v6.0.3 JobStore contract (Protocol + InMemoryJobStore).

Test-first: defines the contract before the implementation exists.
Groups: A. JobStatus enum, B. Job dataclass, C. JobStore Protocol,
D. InMemoryJobStore.
"""
import inspect
from dataclasses import FrozenInstanceError, MISSING, fields
from datetime import datetime
from typing import Protocol, get_type_hints

import pytest

from src.api.job_store import Job, JobStatus, JobStore
from src.api.job_store_memory import InMemoryJobStore


# ============================================================
# A. JobStatus enum
# ============================================================

def test_job_status_members():
    assert {m.name for m in JobStatus} == {"QUEUED", "RUNNING", "DONE", "FAILED"}


def test_job_status_queued_value():
    assert JobStatus.QUEUED.value == "queued"


# ============================================================
# B. Job dataclass
# ============================================================

def test_job_is_frozen():
    now = datetime.now()
    job = Job(
        job_id="job-1",
        status=JobStatus.QUEUED,
        created_at=now,
        updated_at=now,
        filename="x.py",
    )
    with pytest.raises(FrozenInstanceError):
        job.status = JobStatus.RUNNING


def test_job_field_types():
    hints = get_type_hints(Job)
    assert set(hints) == {
        "job_id", "status", "created_at", "updated_at",
        "tenant_id", "filename", "result", "error",
        "started_at", "finished_at",
    }
    assert hints["job_id"] is str
    assert hints["status"] is JobStatus
    assert hints["created_at"] is datetime
    assert hints["updated_at"] is datetime
    assert hints["filename"] is str


def test_job_defaults():
    f = {x.name: x for x in fields(Job)}
    for name in ("tenant_id", "result", "error", "started_at", "finished_at"):
        assert f[name].default is None, name


def test_job_required_fields():
    f = {x.name: x for x in fields(Job)}
    for name in ("job_id", "status", "created_at", "updated_at", "filename"):
        assert f[name].default is MISSING, name


# ============================================================
# C. JobStore Protocol
# ============================================================

def test_jobstore_is_protocol():
    assert issubclass(JobStore, Protocol)


def test_jobstore_declares_all_methods():
    for name in ("create", "get", "update", "delete", "list_jobs", "clear", "count"):
        assert hasattr(JobStore, name), name


def test_jobstore_create_signature():
    sig = inspect.signature(JobStore.create)
    assert sig.parameters["tenant_id"].kind == inspect.Parameter.KEYWORD_ONLY
    with pytest.raises(TypeError):
        InMemoryJobStore().create("x", "t1")  # tenant_id позиционно


# ============================================================
# D. InMemoryJobStore
# ============================================================

@pytest.mark.asyncio
async def test_create_returns_job():
    store = InMemoryJobStore()
    job = await store.create("x.py")
    assert isinstance(job, Job)
    assert job.job_id
    assert job.status is JobStatus.QUEUED


@pytest.mark.asyncio
async def test_create_filename_and_tenant():
    store = InMemoryJobStore()
    job = await store.create(filename="x.py", tenant_id="t1")
    assert job.filename == "x.py"
    assert job.tenant_id == "t1"
    fetched = await store.get(job.job_id)
    assert fetched is not None
    assert fetched.tenant_id == "t1"
    assert (await store.create("y.py")).tenant_id is None


@pytest.mark.asyncio
async def test_get_returns_job_or_none():
    store = InMemoryJobStore()
    job = await store.create("x.py")
    assert (await store.get(job.job_id)).job_id == job.job_id
    assert await store.get("nonexistent") is None


@pytest.mark.asyncio
async def test_update_returns_job_and_bumps_updated_at():
    store = InMemoryJobStore()
    job = await store.create("x.py")
    updated = await store.update(
        job.job_id, status=JobStatus.RUNNING, started_at=datetime.now()
    )
    assert updated is not None
    assert updated.status is JobStatus.RUNNING
    assert updated.started_at is not None
    assert updated.updated_at >= job.updated_at  # bumped (monotonic)


@pytest.mark.asyncio
async def test_update_missing_returns_none():
    store = InMemoryJobStore()
    assert await store.update("nonexistent", status=JobStatus.DONE) is None


@pytest.mark.asyncio
async def test_delete_list_clear_count():
    store = InMemoryJobStore()
    ids = [(await store.create(f"f{i}.py")).job_id for i in range(3)]
    # newest-last == creation order (deterministic via job_id, not micros)
    assert [j.job_id for j in await store.list_jobs()] == ids
    assert [j.job_id for j in await store.list_jobs(limit=2)] == ids[-2:]
    assert await store.delete(ids[0]) is True
    assert await store.delete("nonexistent") is False
    assert await store.count() == 2
    assert await store.clear() == 2
    assert await store.count() == 0
