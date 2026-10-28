# -*- coding: utf-8 -*-
"""hash tenant API keys

Revision ID: 005_add_api_key_hash
Revises: 004_add_tenants
Create Date: 2026-10-22

API keys are bearer credentials: storing them in plaintext means a database dump
(or a read-only SQL injection) hands out working keys. This revision adds
``api_key_hash`` (sha256 hex), backfills it from the existing plaintext column so
already-issued keys keep working, and relaxes ``api_key`` to nullable so new rows
store nothing there.

The plaintext column is **not dropped**: existing deployments may still be
rolling back, and the backfill needs it once. Once every key has been rotated,
a follow-up revision can drop it.
"""
import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_add_api_key_hash"
down_revision: Union[str, None] = "004_add_tenants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("api_key_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_tenants_api_key_hash", "tenants", ["api_key_hash"], unique=True
    )

    # Backfill in Python rather than SQL: sha256() availability differs between
    # PostgreSQL versions, hashlib does not.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT tenant_id, api_key FROM tenants WHERE api_key IS NOT NULL")
    ).fetchall()
    for tenant_id, api_key in rows:
        if not api_key:
            continue
        connection.execute(
            sa.text("UPDATE tenants SET api_key_hash = :digest WHERE tenant_id = :tenant"),
            {"digest": hashlib.sha256(api_key.encode("utf-8")).hexdigest(), "tenant": tenant_id},
        )

    # New rows store only the hash; the old column stays for rollback.
    op.alter_column(
        "tenants", "api_key", existing_type=sa.String(length=128), nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        "tenants", "api_key", existing_type=sa.String(length=128), nullable=False
    )
    op.drop_index("ix_tenants_api_key_hash", table_name="tenants")
    op.drop_column("tenants", "api_key_hash")
