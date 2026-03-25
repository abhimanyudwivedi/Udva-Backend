"""SQLAlchemy ORM model for the competitors table (rival brands tracked per brand)."""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Competitor(Base):
    """A competitor brand tracked alongside a user's brand for visibility comparison."""

    __tablename__ = "competitors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="competitors")  # noqa: F821
