"""SQLAlchemy ORM model for the credit_ledger table (Pillar 3 billing)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CreditLedger(Base):
    """Double-entry ledger tracking credit top-ups and spend per brand."""

    __tablename__ = "credit_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delta: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="positive = top-up, negative = spend"
    )
    reason: Mapped[str] = mapped_column(
        String, nullable=False, comment="plan_credit | topup | comment | post | refund"
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="credit_ledger")  # noqa: F821
    campaign: Mapped["Campaign | None"] = relationship(  # noqa: F821
        "Campaign", back_populates="credit_entries"
    )
