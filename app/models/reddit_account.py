"""SQLAlchemy ORM model for the reddit_accounts table (managed account pool — Pillar 3)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RedditAccount(Base):
    """An aged Reddit account in the managed pool used for Pillar 3 engagement posts."""

    __tablename__ = "reddit_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    encrypted_pw: Mapped[str] = mapped_column(
        String, nullable=False, comment="AES-256 encrypted password"
    )
    proxy_ip: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Dedicated residential proxy IP for this account"
    )
    karma: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    account_age_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="warming",
        comment="warming | active | resting | banned",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_warmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
