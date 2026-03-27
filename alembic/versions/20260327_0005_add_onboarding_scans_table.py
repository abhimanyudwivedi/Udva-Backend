"""Add onboarding_scans table for caching scan results.

Revision ID: 20260327_0005
Revises: 20260325_0004
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "20260327_0005"
down_revision = "20260325_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_scans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("brand_name", sa.String(), nullable=False),
        sa.Column("prompt_used", sa.Text(), nullable=False),
        sa.Column("results", JSON, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_onboarding_scans_brand_id", "onboarding_scans", ["brand_id"])


def downgrade() -> None:
    op.drop_index("ix_onboarding_scans_brand_id", table_name="onboarding_scans")
    op.drop_table("onboarding_scans")
