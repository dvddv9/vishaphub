# -*- coding: utf-8 -*-
"""enable row level security on jobs (tenant isolation)

Revision ID: 002_add_rls_jobs
Revises: 001_initial_jobs
Create Date: 2026-10-20

Notes on deliberate deviations from the first draft of this migration:

* The index ``ix_jobs_tenant_id`` is **already created** by revision
  ``001_initial_jobs``; creating it again would fail with
  "relation already exists". Only a composite index is added here.
* ``CREATE ROLE`` requires superuser (or CREATEROLE). It is wrapped so that a
  less privileged deployment user gets a NOTICE instead of a failed migration.
* RLS is ENABLED but not FORCED: the table owner (the app's own role in most
  deployments) bypasses policies. Protection applies once the application
  connects as ``vishap_app``, which is why that role is provisioned below.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002_add_rls_jobs"
down_revision: Union[str, None] = "001_initial_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Tenant written into rows that predate multi-tenancy. Must match
#: ``DEFAULT_TENANT`` in src/api/job_store.py.
DEFAULT_TENANT = "public"

POLICY_NAME = "tenant_isolation_policy"


def upgrade() -> None:
    # 1. Dedicated, non-owner role for the application (RLS does not apply to
    #    the table owner, so the app must not connect as the owner).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vishap_app') THEN
                CREATE ROLE vishap_app NOLOGIN;
            END IF;
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE 'Skipping role creation: insufficient privilege.';
        END $$;
        """
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE jobs TO vishap_app;
        EXCEPTION
            WHEN undefined_object OR insufficient_privilege THEN
                RAISE NOTICE 'Skipping grants for vishap_app.';
        END $$;
        """
    )

    # 2. Backfill legacy rows so they belong to a tenant instead of NULL.
    op.execute(
        f"UPDATE jobs SET tenant_id = '{DEFAULT_TENANT}' WHERE tenant_id IS NULL;"
    )

    # 3. Enable RLS on jobs.
    op.execute("ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;")

    # 4. Tenant isolation policy: SELECT/INSERT/UPDATE/DELETE are all filtered.
    #    current_setting(..., true) returns NULL when no tenant was set, and
    #    `tenant_id = NULL` is never true — so the policy fails closed.
    #    DROP IF EXISTS keeps the migration re-runnable after a partial failure.
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON jobs;")
    op.execute(
        f"""
        CREATE POLICY {POLICY_NAME} ON jobs
        FOR ALL
        USING (tenant_id = current_setting('app.current_tenant', true))
        WITH CHECK (tenant_id = current_setting('app.current_tenant', true));
        """
    )

    # 5. Composite index for the common tenant + recency listing query.
    #    A plain tenant_id index already exists (001_initial_jobs).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_jobs_tenant_created "
        "ON jobs (tenant_id, created_at);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jobs_tenant_created;")
    op.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON jobs;")
    op.execute("ALTER TABLE jobs DISABLE ROW LEVEL SECURITY;")
