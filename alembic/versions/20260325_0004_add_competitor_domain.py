"""Add domain column to competitors table.

Revision ID: 20260325_0004
Revises: 20260323_0003_rename_stripe_to_dodo
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa

revision = "20260325_0004"
down_revision = "20260323_0003_rename_stripe_to_dodo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("competitors", sa.Column("domain", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("competitors", "domain")
