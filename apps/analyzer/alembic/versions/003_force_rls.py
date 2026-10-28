# -*- coding: utf-8 -*-
"""force row level security on jobs

Revision ID: 003_force_rls
Revises: 002_add_rls_jobs
Create Date: 2026-10-21

Revision 002 enabled RLS, but the table owner still bypasses policies. FORCE
makes the owner subject to them as well — that is the point of this revision.

**Prerequisite, do not apply blindly:** every code path that touches ``jobs``
must bind a tenant first (``tenant_scope``). As of v6.3 that is true for
``POST /analyze/async``, ``GET /status/{id}``, ``GET /report/{id}`` and the
Celery worker. Any unaudited path, ad-hoc SQL session or admin script that
connects as the owner will see **zero rows** once this runs.

Superusers and roles with BYPASSRLS are still exempt — that is why the app must
connect as ``vishap_app`` (provisioned in 002), not as the owner.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003_force_rls"
down_revision: Union[str, None] = "002_add_rls_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TABLE ... FORCE is idempotent: re-running it is a no-op.
    op.execute("ALTER TABLE jobs FORCE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("ALTER TABLE jobs NO FORCE ROW LEVEL SECURITY;")
