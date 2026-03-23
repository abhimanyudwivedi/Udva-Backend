"""SQLAlchemy ORM model for the users table."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """Represents an Udva customer account."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    hashed_pw: Mapped[str] = mapped_column(String, nullable=False)
    plan: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="trial",
        comment="trial | starter | growth | enterprise",
    )
    dodo_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    dodo_sub_id: Mapped[str | None] = mapped_column(String, nullable=True)
    alert_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    slack_webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    brands: Mapped[list["Brand"]] = relationship(  # noqa: F821
        "Brand", back_populates="owner", cascade="all, delete-orphan"
    )
