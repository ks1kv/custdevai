"""Согласие респондента на обработку данных (FR-BOT-01, № 152-ФЗ)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from apps.api.db.base import Base


class Consent(Base):
    """Факт явного согласия респондента на участие в исследовании.

    1:1 с InterviewSession через UNIQUE на session_id. Записи иммутабельны
    (без updated_at) — отзыв согласия в Phase 2 не реализуется
    (см. FR-DB-07, отложено в Phase 5).
    """

    __tablename__ = "consents"
    __table_args__ = (Index("ix_consents_granted_at", "granted_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    # SHA-256(ip + master_salt) — IP в открытом виде не сохраняется (NFR-SEC-08).
    ip_address_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
