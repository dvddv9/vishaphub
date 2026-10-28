"""rename stripe_customer_id to ls_customer_id

Revision ID: 6689026fa1b5
Revises: 005_add_api_key_hash
Create Date: 2026-10-25 02:16:15.228578

Hand-written: autogenerate proposed drop_column+add_column (data loss)
plus unrelated index/constraint churn on api_key / api_key_hash.
Those are a separate model/schema drift and are out of scope here.
This revision does the minimal safe operation: rename in place.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '6689026fa1b5'
down_revision: Union[str, None] = '005_add_api_key_hash'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('tenants', 'stripe_customer_id', new_column_name='ls_customer_id',
                    existing_type=None, existing_nullable=True)


def downgrade() -> None:
    op.alter_column('tenants', 'ls_customer_id', new_column_name='stripe_customer_id',
                    existing_type=None, existing_nullable=True)
