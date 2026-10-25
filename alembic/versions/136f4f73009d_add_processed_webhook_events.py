"""add processed_webhook_events

Revision ID: 136f4f73009d
Revises: 6689026fa1b5
Create Date: 2026-10-25 07:14:05.113171

Hand-written: autogenerate proposed unrelated index/constraint churn
on tenants (api_key / api_key_hash). That is a separate model/schema
drift and is out of scope here. This revision only creates the
idempotency table for Lemon Squeezy webhooks.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '136f4f73009d'
down_revision: Union[str, None] = '6689026fa1b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'processed_webhook_events',
        sa.Column('event_id', sa.String(length=128), nullable=False),
        sa.Column('event_name', sa.String(length=64), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('event_id'),
    )


def downgrade() -> None:
    op.drop_table('processed_webhook_events')