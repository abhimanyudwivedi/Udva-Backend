"""SQLAlchemy ORM model for the brands table."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Brand(Base):
    """A brand tracked by an Udva user. One user can own multiple brands (plan-limited)."""

    __tablename__ = "brands"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="brands")  # noqa: F821
    queries: Mapped[list["Query"]] = relationship(  # noqa: F821
        "Query", back_populates="brand", cascade="all, delete-orphan"
    )
    keywords: Mapped[list["Keyword"]] = relationship(  # noqa: F821
        "Keyword", back_populates="brand", cascade="all, delete-orphan"
    )
    visibility_scores: Mapped[list["VisibilityScore"]] = relationship(  # noqa: F821
        "VisibilityScore", back_populates="brand", cascade="all, delete-orphan"
    )
    citation_sources: Mapped[list["CitationSource"]] = relationship(  # noqa: F821
        "CitationSource", back_populates="brand", cascade="all, delete-orphan"
    )
    mentions: Mapped[list["Mention"]] = relationship(  # noqa: F821
        "Mention", back_populates="brand", cascade="all, delete-orphan"
    )
    campaigns: Mapped[list["Campaign"]] = relationship(  # noqa: F821
        "Campaign", back_populates="brand", cascade="all, delete-orphan"
    )
    credit_ledger: Mapped[list["CreditLedger"]] = relationship(  # noqa: F821
        "CreditLedger", back_populates="brand", cascade="all, delete-orphan"
    )
    competitors: Mapped[list["Competitor"]] = relationship(  # noqa: F821
        "Competitor", back_populates="brand", cascade="all, delete-orphan"
    )
