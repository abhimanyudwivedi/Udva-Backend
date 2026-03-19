"""SQLAlchemy ORM model for the visibility_scores table (Pillar 1 output)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VisibilityScore(Base):
    """One row per query × model × day capturing whether and how a brand was mentioned."""

    __tablename__ = "visibility_scores"

    __table_args__ = (
        Index("ix_visibility_scores_brand_scored", "brand_id", "scored_at"),
        Index("ix_visibility_scores_query_model_scored", "query_id", "model", "scored_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("queries.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="gpt-4o | claude-sonnet-4-6 | gemini-2.5-flash",
    )
    brand_mentioned: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mention_rank: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="1 = first mention, NULL = not mentioned"
    )
    sentiment: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="positive | neutral | negative | NULL"
    )
    is_competitor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    query: Mapped["Query"] = relationship("Query", back_populates="visibility_scores")  # noqa: F821
    brand: Mapped["Brand"] = relationship("Brand", back_populates="visibility_scores")  # noqa: F821
