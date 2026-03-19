"""add user settings columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-18 00:01:00.000000

Adds two columns to the ``users`` table to support per-user alert settings:

- ``alert_threshold`` (Integer, NOT NULL, server default 60)
- ``slack_webhook_url`` (Text, nullable)
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "alert_threshold",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )
    op.add_column(
        "users",
        sa.Column("slack_webhook_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "slack_webhook_url")
    op.drop_column("users", "alert_threshold")
