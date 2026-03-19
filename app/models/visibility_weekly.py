"""SQLAlchemy ORM model for the visibility_weekly table (Pillar 1 rollup)."""

import uuid
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VisibilityWeekly(Base):
    """Weekly aggregated visibility scores — one row per brand × model × week.

    Populated by the Monday 3AM UTC ``compute_weekly_task`` Celery task from
    the raw ``visibility_scores`` rows written by the daily LLM dispatch.
    """

    __tablename__ = "visibility_weekly"

    __table_args__ = (
        UniqueConstraint(
            "brand_id", "model", "week_start",
            name="uq_visibility_weekly_brand_model_week",
        ),
        Index("ix_visibility_weekly_brand_week", "brand_id", "week_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(
        String, nullable=False, comment="gpt-4o | claude-sonnet-4-6 | gemini-2.5-flash"
    )
    week_start: Mapped[date] = mapped_column(
        Date, nullable=False, comment="Monday of the ISO week (UTC)"
    )
    total_queries: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Number of query×model rows in the week"
    )
    mentioned_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Rows where brand_mentioned = true"
    )
    mention_rate: Mapped[float] = mapped_column(
        Float, nullable=False, comment="mentioned_count / total_queries × 100"
    )
    avg_rank: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Mean mention_rank across mentioned rows; NULL if never mentioned",
    )

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand")  # noqa: F821
