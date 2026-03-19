"""SQLAlchemy ORM model for the queries table (prompts sent to LLMs — Pillar 1)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Query(Base):
    """A tracked prompt that is sent to LLMs to measure brand visibility."""

    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="queries")  # noqa: F821
    visibility_scores: Mapped[list["VisibilityScore"]] = relationship(  # noqa: F821
        "VisibilityScore", back_populates="query", cascade="all, delete-orphan"
    )
    citation_sources: Mapped[list["CitationSource"]] = relationship(  # noqa: F821
        "CitationSource", back_populates="query"
    )
