"""Rename stripe_* columns to dodo_*, add dodo_sub_id

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "stripe_customer_id", new_column_name="dodo_customer_id")
    op.alter_column("users", "stripe_sub_id", new_column_name="dodo_sub_id")


def downgrade() -> None:
    op.alter_column("users", "dodo_customer_id", new_column_name="stripe_customer_id")
    op.alter_column("users", "dodo_sub_id", new_column_name="stripe_sub_id")
