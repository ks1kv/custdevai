"""Модель Campaign (кампания сбора данных)."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db.base import Base, TimestampMixin


class CampaignStatus(str, enum.Enum):
    """Допустимые состояния кампании (см. ENUM campaign_status)."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class Campaign(Base, TimestampMixin):
    """Кампания сбора данных, привязанная к одному сценарию."""

    __tablename__ = "campaigns"
    __table_args__ = (Index("ix_campaigns_status_created_at", "status", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    script_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("scripts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status", create_constraint=True),
        nullable=False,
        default=CampaignStatus.DRAFT,
        index=True,
    )
    # Per-campaign соль для SHA-256 хеширования telegram_id (FR-DB-03).
    pseudonym_salt: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    invitation_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
