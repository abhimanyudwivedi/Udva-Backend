"""add visibility_weekly table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-18 00:02:00.000000

Creates ``visibility_weekly`` — the Pillar 1 weekly rollup table populated
by ``app.tasks.rollup.compute_weekly_task`` every Monday at 3AM UTC.

One row per brand × model × week_start (Monday of the ISO week).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visibility_weekly",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "brand_id",
            UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("total_queries", sa.Integer(), nullable=False),
        sa.Column("mentioned_count", sa.Integer(), nullable=False),
        sa.Column("mention_rate", sa.Float(), nullable=False),
        sa.Column("avg_rank", sa.Float(), nullable=True),
    )

    op.create_unique_constraint(
        "uq_visibility_weekly_brand_model_week",
        "visibility_weekly",
        ["brand_id", "model", "week_start"],
    )

    op.create_index(
        "ix_visibility_weekly_brand_week",
        "visibility_weekly",
        ["brand_id", "week_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_visibility_weekly_brand_week", table_name="visibility_weekly")
    op.drop_constraint(
        "uq_visibility_weekly_brand_model_week",
        "visibility_weekly",
        type_="unique",
    )
    op.drop_table("visibility_weekly")
