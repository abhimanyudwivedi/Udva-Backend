"""SQLAlchemy ORM model for the mentions table (Social Listening — Pillar 2)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Mention(Base):
    """A social post (Reddit thread, Quora page, etc.) that mentions a tracked keyword."""

    __tablename__ = "mentions"

    __table_args__ = (
        Index("ix_mentions_brand_relevance_found", "brand_id", "relevance_score", "found_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    keyword_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("keywords.id"), nullable=True
    )
    platform: Mapped[str] = mapped_column(
        String, nullable=False, comment="reddit | quora | facebook"
    )
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    content_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    engagement: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="upvotes / score"
    )
    google_rank: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="1-10 if on page 1, NULL otherwise"
    )
    relevance_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="0-100, computed by relevance_scorer"
    )
    url_hash: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True, comment="MD5(url + brand_id) for dedup"
    )
    found_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="mentions")  # noqa: F821
    keyword: Mapped["Keyword | None"] = relationship("Keyword", back_populates="mentions")  # noqa: F821
