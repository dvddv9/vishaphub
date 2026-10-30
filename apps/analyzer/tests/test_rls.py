# -*- coding: utf-8 -*-
"""Multi-tenant isolation (RLS) tests - unit plus Postgres integration.

The integration tests need a Postgres where TEST_POSTGRES_URL names a superuser (they
create a database of their own, run the migrations there and reach it as ``vishap_app``):

    $env:TEST_POSTGRES_URL="postgresql+asyncpg://vishap:vishap_dev@localhost:5432/vishap"
    python -m pytest tests/test_rls.py -v

Without TEST_POSTGRES_URL the integration tests are skipped - that is the only way they
skip. With it, a missing policy, a missing role or a role that bypasses RLS is a failure:
a test that skips when isolation is absent proves nothing about isolation.
"""
import asyncio
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.api import jobs as jobs_module
from src.api.job_store import DEFAULT_TENANT, get_tenant, set_tenant, tenant_scope
from src.api.job_store_memory import InMemoryJobStore
from src.auth.middleware import _claims_to_identity, current_user

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "alembic" / "versions" / "002_add_rls_jobs.py"
PG_URL = os.getenv("TEST_POSTGRES_URL", "")


APP_ROLE = "vishap_app"
APP_PASSWORD = "vishap_app_test_only"
RLS_DB = "vishap_rls_test"


def _pg_url(role: str | None = None, database: str | None = None) -> str:
    from sqlalchemy.engine import make_url

    url = make_url(PG_URL)
    if role:
        url = url.set(username=role, password=APP_PASSWORD)
    if database:
        url = url.set(database=database)
    return url.render_as_string(hide_password=False)


async def _admin(sql: str):
    """Run one statement as the admin of TEST_POSTGRES_URL (autocommit: DDL on databases and roles)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_pg_url(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql))
            return result.first() if result.returns_rows else None
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def rls_url():
    """A database of its own, migrated to head, reached as ``vishap_app``.

    The job-store integration tests drop and recreate ``jobs`` - and its policy with it -
    so isolation cannot be checked on their database. Here the migrations run for real,
    in a scratch database, and the connection is the application's role, not the admin.
    Everything is removed afterwards, the role goes back to NOLOGIN as migration 002 made it.
    """
    if not PG_URL:
        pytest.skip("TEST_POSTGRES_URL not set")
    asyncio.run(_admin(f"DROP DATABASE IF EXISTS {RLS_DB} WITH (FORCE)"))
    asyncio.run(_admin(f"CREATE DATABASE {RLS_DB}"))
    try:
        run = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, capture_output=True, text=True,
            env={**os.environ, "DATABASE_URL": _pg_url(database=RLS_DB)}, check=False,
        )
        assert run.returncode == 0, run.stderr[-2000:]
        asyncio.run(_admin(f"ALTER ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}'"))
        flags = asyncio.run(_admin(
            f"SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = '{APP_ROLE}'"))
        assert tuple(flags) == (False, False), f"{APP_ROLE} must be NOSUPERUSER NOBYPASSRLS, got {flags}"
        yield _pg_url(APP_ROLE, RLS_DB)
    finally:
        try:
            asyncio.run(_admin(f"ALTER ROLE {APP_ROLE} NOLOGIN PASSWORD NULL"))
        except Exception:  # noqa: BLE001 - the role may not exist if the migration itself failed
            pass
        asyncio.run(_admin(f"DROP DATABASE IF EXISTS {RLS_DB} WITH (FORCE)"))


@pytest.fixture(autouse=True)
def _reset_tenant():
    """Never leak tenant context between tests."""
    set_tenant(None)
    yield
    set_tenant(None)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_002", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ============================================================
# A. Tenant context primitives
# ============================================================

def test_set_and_get_tenant():
    assert get_tenant() is None
    set_tenant("org-123")
    assert get_tenant() == "org-123"


def test_tenant_scope_restores_previous_value():
    set_tenant("outer")
    with tenant_scope("inner"):
        assert get_tenant() == "inner"
    assert get_tenant() == "outer"


def test_tenant_scope_restores_on_exception():
    with pytest.raises(RuntimeError):
        with tenant_scope("t1"):
            raise RuntimeError("boom")
    assert get_tenant() is None


# ============================================================
# B. Clerk -> tenant mapping
# ============================================================

def test_claims_to_identity_prefers_org_id():
    identity = _claims_to_identity({"sub": "user-1", "org_id": "org-9"})
    assert identity["user_id"] == "user-1"
    assert identity["tenant_id"] == "org-9"


def test_claims_to_identity_falls_back_to_user_id():
    identity = _claims_to_identity({"sub": "user-1"})
    assert identity["tenant_id"] == "user-1"


def test_current_user_dependency_returns_tenant_id():
    api = FastAPI()

    @api.get("/whoami")
    async def whoami(user=Depends(current_user)):
        return user

    client = TestClient(api)
    with patch(
        "src.auth.middleware.verify_jwt",
        return_value={"sub": "user-1", "org_id": "org-9"},
    ):
        response = client.get("/whoami", headers={"Authorization": "Bearer stub"})

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "org-9"
    assert body["user_id"] == "user-1"


# ============================================================
# C. In-memory store isolation
# ============================================================

@pytest.mark.asyncio
async def test_memory_store_isolates_tenants():
    store = InMemoryJobStore()

    set_tenant("t1")
    job_t1 = await store.create("a.py")
    set_tenant("t2")
    job_t2 = await store.create("b.py")

    set_tenant("t1")
    assert await store.get(job_t1.job_id) is not None
    assert await store.get(job_t2.job_id) is None
    assert [j.job_id for j in await store.list_jobs()] == [job_t1.job_id]
    assert await store.count() == 1
    assert await store.delete(job_t2.job_id) is False


@pytest.mark.asyncio
async def test_memory_store_unscoped_sees_everything():
    store = InMemoryJobStore()
    set_tenant("t1")
    await store.create("a.py")
    set_tenant("t2")
    await store.create("b.py")

    set_tenant(None)
    assert await store.count() == 2
    assert len(await store.list_jobs()) == 2


@pytest.mark.asyncio
async def test_memory_create_inherits_bound_tenant():
    store = InMemoryJobStore()
    set_tenant("t1")
    job = await store.create("a.py")
    assert job.tenant_id == "t1"


@pytest.mark.asyncio
async def test_memory_create_explicit_tenant_wins():
    store = InMemoryJobStore()
    set_tenant("t1")
    job = await store.create("a.py", tenant_id="t2")
    assert job.tenant_id == "t2"


def test_jobs_shim_passes_tenant_id():
    store = InMemoryJobStore()
    with patch.object(jobs_module, "get_store", return_value=store):
        job_id = jobs_module.create_job("a.py", tenant_id="t1")
        set_tenant("t1")
        assert jobs_module.get_job(job_id)["tenant_id"] == "t1"
        set_tenant("t2")
        assert jobs_module.get_job(job_id) is None


# ============================================================
# D. Postgres store emits the tenant GUC (mocked session)
# ============================================================

@pytest.fixture
def pg_store():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.delete = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.rowcount = 0
    result.scalar.return_value = 0
    session.execute = AsyncMock(return_value=result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)

    with patch("src.api.job_store_postgres.create_async_engine", return_value=MagicMock()), \
         patch("src.api.job_store_postgres.async_sessionmaker", return_value=factory):
        from src.api.job_store_postgres import PostgresJobStore
        store = PostgresJobStore("postgresql+asyncpg://u:p@localhost/db")
    return store, session


@pytest.mark.asyncio
async def test_postgres_session_applies_tenant(pg_store):
    store, session = pg_store
    store.set_tenant("t1")
    await store.list_jobs()

    first = session.execute.await_args_list[0]
    assert "set_config" in str(first.args[0])
    assert first.args[1] == {"tenant": "t1"}


@pytest.mark.asyncio
async def test_postgres_session_skips_tenant_when_unset(pg_store):
    store, session = pg_store
    store.set_tenant(None)
    await store.list_jobs()

    assert all("set_config" not in str(call.args[0]) for call in session.execute.await_args_list)


@pytest.mark.asyncio
async def test_postgres_create_tags_bound_tenant(pg_store):
    store, session = pg_store
    store.set_tenant("t1")
    job = await store.create("a.py")
    assert job.tenant_id == "t1"


@pytest.mark.asyncio
async def test_postgres_store_is_a_jobstore(pg_store):
    store, _ = pg_store
    for name in ("create", "get", "update", "delete", "list_jobs", "clear", "count",
                 "set_tenant", "get_tenant"):
        assert hasattr(store, name), name


# ============================================================
# E. Migration shape (no database required)
# ============================================================

def test_migration_enables_rls_and_policy():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "CREATE POLICY" in source
    assert "tenant_isolation_policy" in source
    assert "current_setting('app.current_tenant', true)" in source
    assert "DROP POLICY IF EXISTS" in source


def test_migration_revision_chain():
    module = _load_migration()
    assert module.revision == "002_add_rls_jobs"
    assert module.down_revision == "001_initial_jobs"


def test_migration_does_not_duplicate_existing_index():
    """001_initial_jobs already creates ix_jobs_tenant_id, so 002 must not recreate it."""
    source = MIGRATION.read_text(encoding="utf-8")
    assert '"ix_jobs_tenant_id"' not in source


# ============================================================
# F. Postgres integration (requires TEST_POSTGRES_URL)
# ============================================================

@pytest.mark.asyncio
async def test_rls_policy_exists_in_pg(rls_url):
    """After the migrations the table has the tenant policy, with RLS enabled and forced."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(rls_url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT p.polname, c.relrowsecurity, c.relforcerowsecurity FROM pg_policy p "
                        "JOIN pg_class c ON c.oid = p.polrelid WHERE c.relname = 'jobs'"
                    )
                )
            ).all()
    finally:
        await engine.dispose()

    policy = [row for row in rows if row[0] == "tenant_isolation_policy"]
    assert policy, f"tenant_isolation_policy is missing (rows={rows})"
    assert policy[0][1] is True and policy[0][2] is True, policy


@pytest.mark.asyncio
async def test_tenant_isolation_in_pg(rls_url):
    """Two tenants cannot read each other's jobs through the app role."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.api.job_store_postgres import PostgresJobStore

    engine = create_async_engine(rls_url)
    async with engine.connect() as conn:
        who = (await conn.execute(text("SELECT current_user, current_setting('is_superuser')"))).one()
    await engine.dispose()
    assert tuple(who) == (APP_ROLE, "off"), who

    store = PostgresJobStore(rls_url)
    try:
        store.set_tenant("tenant-a")
        job_a = await store.create("a.py")
        store.set_tenant("tenant-b")
        job_b = await store.create("b.py")

        store.set_tenant("tenant-a")
        assert await store.get(job_a.job_id) is not None      # isolation is not "nobody sees anything"
        store.set_tenant("tenant-b")
        assert await store.get(job_a.job_id) is None
        assert await store.get(job_b.job_id) is not None
    finally:
        try:
            store.set_tenant("tenant-a")
            await store.delete(job_a.job_id)
            store.set_tenant("tenant-b")
            await store.delete(job_b.job_id)
        finally:
            set_tenant(None)
            await store._engine.dispose()


def test_default_tenant_matches_migration():
    module = _load_migration()
    assert module.DEFAULT_TENANT == DEFAULT_TENANT


def test_inmemory_store_satisfies_protocol_shape():
    store = InMemoryJobStore()
    for name in ("create", "get", "update", "delete", "list_jobs", "clear", "count",
                 "set_tenant", "get_tenant"):
        assert hasattr(store, name), name


# ============================================================
# G. Context isolation and HTTP-level tenant enforcement
# ============================================================

@pytest.mark.asyncio
async def test_tenant_scope_does_not_leak_between_tasks():
    """Concurrent requests must not see each other's tenant."""

    async def worker(tenant_id: str, delay: float) -> str | None:
        with tenant_scope(tenant_id):
            await asyncio.sleep(delay)
            return get_tenant()

    results = await asyncio.gather(worker("t1", 0.02), worker("t2", 0.0))
    assert results == ["t1", "t2"]
    assert get_tenant() is None


def test_status_and_report_hide_other_tenants():
    """A job owned by tenant-a is invisible to tenant-b (404, not 403)."""
    from fastapi.testclient import TestClient

    from src.auth.middleware import current_tenant
    from src.main import app

    job_id = jobs_module.create_job("a.py", tenant_id="tenant-a")
    client = TestClient(app)
    try:
        app.dependency_overrides[current_tenant] = lambda: "tenant-b"
        assert client.get(f"/status/{job_id}").status_code == 404
        assert client.get(f"/report/{job_id}").status_code == 404

        app.dependency_overrides[current_tenant] = lambda: "tenant-a"
        assert client.get(f"/status/{job_id}").status_code == 200
        assert client.get(f"/report/{job_id}").status_code == 409  # queued, not done
    finally:
        app.dependency_overrides.pop(current_tenant, None)


@pytest.mark.asyncio
async def test_postgres_fail_closed_without_tenant(rls_url):
    """No tenant set -> RLS denies everything (no rows, no exception), even when rows exist."""
    from src.api.job_store_postgres import PostgresJobStore

    store = PostgresJobStore(rls_url)
    try:
        store.set_tenant("tenant-a")
        job = await store.create("a.py")
        assert await store.count() == 1                       # the row is really there

        set_tenant(None)
        assert await store.list_jobs() == []
        assert await store.count() == 0
    finally:
        try:
            store.set_tenant("tenant-a")
            await store.delete(job.job_id)
        finally:
            set_tenant(None)
            await store._engine.dispose()