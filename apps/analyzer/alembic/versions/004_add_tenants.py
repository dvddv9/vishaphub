# -*- coding: utf-8 -*-
"""tenants table for manual (SWIFT) billing

Revision ID: 004_add_tenants
Revises: 003_force_rls
Create Date: 2026-10-22

One row per paying tenant. `api_key` is the credential issued by
`scripts/generate_key.py` after a bank transfer arrives; `expires_at` is what
`verify_tenant_api_key` checks on every request.

Note on RLS: this table deliberately has **no** row-level security. It is read
*before* a tenant is known (the API key is what identifies the tenant), so a
tenant-scoped policy could never match. Access control here is the column type
plus the fact that only the API process reads it — do not expose this table
through any tenant-scoped query path.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_add_tenants"
down_revision: Union[str, None] = "003_force_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("api_key", sa.String(length=128), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_customer_id", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id"),
        sa.UniqueConstraint("api_key", name="uq_tenants_api_key"),
    )
    op.create_index("ix_tenants_api_key", "tenants", ["api_key"])
    op.create_index("ix_tenants_email", "tenants", ["email"])


def downgrade() -> None:
    op.drop_index("ix_tenants_email", table_name="tenants")
    op.drop_index("ix_tenants_api_key", table_name="tenants")
    op.drop_table("tenants")
