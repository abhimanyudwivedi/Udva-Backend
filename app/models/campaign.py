"""SQLAlchemy ORM model for the campaigns table (Engagement Engine — Pillar 3)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Campaign(Base):
    """An engagement action ordered by a customer — posts a comment or thread to Reddit."""

    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_url: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    post_type: Mapped[str] = mapped_column(
        String, nullable=False, comment="comment | comment_with_link | post"
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="queued",
        comment="queued | posted | removed | refunded",
    )
    reddit_post_id: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Reddit post/comment ID returned after posting"
    )
    upvote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="Which reddit_account posted this"
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="campaigns")  # noqa: F821
    credit_entries: Mapped[list["CreditLedger"]] = relationship(  # noqa: F821
        "CreditLedger", back_populates="campaign"
    )
