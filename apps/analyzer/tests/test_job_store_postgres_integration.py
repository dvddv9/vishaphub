# -*- coding: utf-8 -*-
"""Integration tests for PostgresJobStore (require a live PostgreSQL).

Run against a local Postgres:
    TEST_POSTGRES_URL=postgresql+asyncpg://vishap:vishap_dev@localhost:5432/vishap \
        pytest tests/test_job_store_postgres_integration.py -v
"""
import os

import pytest

from src.api.job_store_postgres import Base, PostgresJobStore

TEST_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(TEST_URL is None, reason="TEST_POSTGRES_URL not set")


def _store() -> PostgresJobStore:
    return PostgresJobStore(TEST_URL)


async def _reset(store: PostgresJobStore) -> None:
    async with store._engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_create_and_get_roundtrip():
    store = _store()
    await _reset(store)
    try:
        job = await store.create("x.py", tenant_id="t1")
        fetched = await store.get(job.job_id)
        assert fetched is not None
        assert fetched.job_id == job.job_id
        assert fetched.filename == "x.py"
        assert fetched.tenant_id == "t1"
    finally:
        await store._engine.dispose()


@pytest.mark.asyncio
async def test_update_changes_status_and_updated_at():
    store = _store()
    await _reset(store)
    try:
        job = await store.create("x.py")
        updated = await store.update(job.job_id, status="running")
        assert updated is not None
        assert updated.status.value == "running"
        assert updated.updated_at >= job.updated_at
    finally:
        await store._engine.dispose()


@pytest.mark.asyncio
async def test_delete_removes_job():
    store = _store()
    await _reset(store)
    try:
        job = await store.create("x.py")
        assert await store.delete(job.job_id) is True
        assert await store.get(job.job_id) is None
    finally:
        await store._engine.dispose()


@pytest.mark.asyncio
async def test_list_jobs_returns_created():
    store = _store()
    await _reset(store)
    try:
        ids = [ (await store.create(f"f{i}.py")).job_id for i in range(3) ]
        jobs = await store.list_jobs()
        got = {j.job_id for j in jobs}
        assert set(ids) <= got
    finally:
        await store._engine.dispose()


@pytest.mark.asyncio
async def test_clear_removes_all():
    store = _store()
    await _reset(store)
    try:
        for i in range(3):
            await store.create(f"f{i}.py")
        assert await store.clear() == 3
        assert await store.count() == 0
    finally:
        await store._engine.dispose()
