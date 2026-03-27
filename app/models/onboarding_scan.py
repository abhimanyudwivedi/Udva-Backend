"""SQLAlchemy ORM model for the onboarding_scans table."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OnboardingScan(Base):
    """Cached result of the onboarding LLM scan for a brand.

    One row per brand — results are stored on first run and returned from cache
    on subsequent calls to avoid re-running expensive LLM API calls.
    """

    __tablename__ = "onboarding_scans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    brand_name: Mapped[str] = mapped_column(String, nullable=False)
    prompt_used: Mapped[str] = mapped_column(Text, nullable=False)
    results: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    brand: Mapped["Brand"] = relationship("Brand")  # noqa: F821
