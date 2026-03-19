"""SQLAlchemy ORM model for the keywords table (Social Listening — Pillar 2)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Keyword(Base):
    """A keyword tracked for a brand across Reddit, Quora, or Facebook."""

    __tablename__ = "keywords"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    keyword: Mapped[str] = mapped_column(String, nullable=False)
    platform: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="reddit",
        comment="reddit | quora | facebook",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="keywords")  # noqa: F821
    mentions: Mapped[list["Mention"]] = relationship(  # noqa: F821
        "Mention", back_populates="keyword"
    )
