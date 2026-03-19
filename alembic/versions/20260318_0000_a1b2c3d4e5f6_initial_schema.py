"""initial schema

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-03-18 00:00:00.000000 UTC

Tables created:
  users, brands, queries, keywords, competitors,
  visibility_scores, citation_sources, mentions,
  campaigns, credit_ledger, reddit_accounts
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all Udva tables in dependency order."""

    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_pw", sa.String(), nullable=False),
        sa.Column(
            "plan",
            sa.String(),
            nullable=False,
            server_default="trial",
            comment="trial | solo | indie | studio | agency",
        ),
        sa.Column("stripe_customer_id", sa.String(), nullable=True),
        sa.Column("stripe_sub_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ------------------------------------------------------------------
    # brands
    # ------------------------------------------------------------------
    op.create_table(
        "brands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_brands_user_id", "brands", ["user_id"])

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    op.create_table(
        "queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_queries_brand_id", "queries", ["brand_id"])

    # ------------------------------------------------------------------
    # keywords
    # ------------------------------------------------------------------
    op.create_table(
        "keywords",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword", sa.String(), nullable=False),
        sa.Column(
            "platform",
            sa.String(),
            nullable=False,
            server_default="reddit",
            comment="reddit | quora | facebook",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_keywords_brand_id", "keywords", ["brand_id"])

    # ------------------------------------------------------------------
    # competitors
    # ------------------------------------------------------------------
    op.create_table(
        "competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_competitors_brand_id", "competitors", ["brand_id"])

    # ------------------------------------------------------------------
    # visibility_scores
    # ------------------------------------------------------------------
    op.create_table(
        "visibility_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "model",
            sa.String(),
            nullable=False,
            comment="gpt-4o | claude-sonnet-4-6 | gemini-2.5-flash",
        ),
        sa.Column("brand_mentioned", sa.Boolean(), nullable=False),
        sa.Column(
            "mention_rank",
            sa.Integer(),
            nullable=True,
            comment="1 = first mention, NULL = not mentioned",
        ),
        sa.Column(
            "sentiment",
            sa.String(),
            nullable=True,
            comment="positive | neutral | negative | NULL",
        ),
        sa.Column("is_competitor", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column(
            "scored_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_id"], ["queries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_visibility_scores_brand_scored",
        "visibility_scores",
        ["brand_id", "scored_at"],
    )
    op.create_index(
        "ix_visibility_scores_query_model_scored",
        "visibility_scores",
        ["query_id", "model", "scored_at"],
    )

    # ------------------------------------------------------------------
    # citation_sources
    # ------------------------------------------------------------------
    op.create_table(
        "citation_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "found_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_id"], ["queries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_citation_sources_brand_id", "citation_sources", ["brand_id"])

    # ------------------------------------------------------------------
    # mentions
    # ------------------------------------------------------------------
    op.create_table(
        "mentions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "platform",
            sa.String(),
            nullable=False,
            comment="reddit | quora | facebook",
        ),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("content_snippet", sa.Text(), nullable=True),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column(
            "engagement",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="upvotes / score",
        ),
        sa.Column(
            "google_rank",
            sa.Integer(),
            nullable=True,
            comment="1-10 if on page 1, NULL otherwise",
        ),
        sa.Column(
            "relevance_score",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="0-100, computed by relevance_scorer",
        ),
        sa.Column(
            "url_hash",
            sa.String(),
            nullable=True,
            unique=True,
            comment="MD5(url + brand_id) for dedup",
        ),
        sa.Column(
            "found_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["keyword_id"], ["keywords.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url_hash"),
    )
    op.create_index(
        "ix_mentions_brand_relevance_found",
        "mentions",
        ["brand_id", "relevance_score", "found_at"],
    )

    # ------------------------------------------------------------------
    # campaigns  (no FK to reddit_accounts — account_id is a bare UUID)
    # ------------------------------------------------------------------
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_url", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "post_type",
            sa.String(),
            nullable=False,
            comment="comment | comment_with_link | post",
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="queued",
            comment="queued | posted | removed | refunded",
        ),
        sa.Column(
            "reddit_post_id",
            sa.String(),
            nullable=True,
            comment="Reddit post/comment ID returned after posting",
        ),
        sa.Column("upvote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_charged", sa.Integer(), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Which reddit_account posted this",
        ),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaigns_brand_id", "campaigns", ["brand_id"])

    # ------------------------------------------------------------------
    # credit_ledger
    # ------------------------------------------------------------------
    op.create_table(
        "credit_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "delta",
            sa.Integer(),
            nullable=False,
            comment="positive = top-up, negative = spend",
        ),
        sa.Column(
            "reason",
            sa.String(),
            nullable=False,
            comment="plan_credit | topup | comment | post | refund",
        ),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_ledger_brand_id", "credit_ledger", ["brand_id"])

    # ------------------------------------------------------------------
    # reddit_accounts  (no FK dependencies — standalone pool table)
    # ------------------------------------------------------------------
    op.create_table(
        "reddit_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column(
            "encrypted_pw",
            sa.String(),
            nullable=False,
            comment="AES-256 encrypted password",
        ),
        sa.Column(
            "proxy_ip",
            sa.String(),
            nullable=True,
            comment="Dedicated residential proxy IP for this account",
        ),
        sa.Column("karma", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("account_age_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="warming",
            comment="warming | active | resting | banned",
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_warmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )


def downgrade() -> None:
    """Drop all Udva tables in reverse dependency order."""
    op.drop_table("reddit_accounts")
    op.drop_table("credit_ledger")
    op.drop_table("campaigns")
    op.drop_table("mentions")
    op.drop_table("citation_sources")
    op.drop_table("visibility_scores")
    op.drop_table("competitors")
    op.drop_table("keywords")
    op.drop_table("queries")
    op.drop_table("brands")
    op.drop_table("users")
