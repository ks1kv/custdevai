"""Модели InterviewSession и Answer."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db.base import Base, TimestampMixin


class SessionStatus(str, enum.Enum):
    """Состояние сессии интервью."""

    ACTIVE = "active"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"


class InterviewSession(Base, TimestampMixin):
    """Одна сессия интервью одного респондента в рамках одной кампании.

    Имя ORM-класса — InterviewSession (а не Session), чтобы избежать
    коллизии с sqlalchemy.orm.Session. Имя таблицы остаётся sessions.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "telegram_id_hash",
            name="uq_sessions_campaign_telegram",
        ),
        # B-Tree индексы для FR-DB-04: фильтрация по кампании и статусу/дате.
        Index("ix_sessions_campaign_status", "campaign_id", "status"),
        Index("ix_sessions_campaign_started", "campaign_id", "started_at"),
        Index("ix_sessions_last_activity", "last_activity_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SHA-256 → 32 байта. Хранится как BYTEA, а не hex-строка — компактнее и
    # исключает случайное логирование как печатного значения.
    telegram_id_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status", create_constraint=True),
        nullable=False,
        default=SessionStatus.ACTIVE,
    )
    progress_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Answer(Base, TimestampMixin):
    """Ответ респондента на конкретный вопрос."""

    __tablename__ = "answers"
    __table_args__ = (
        # FR-API-08: идемпотентность приёма ответов — повторная отправка
        # одного и того же ответа не порождает дубль.
        UniqueConstraint("session_id", "question_id", name="uq_answers_session_question"),
        CheckConstraint(
            "char_length(text) BETWEEN 1 AND 4096",
            name="answers_text_length",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("questions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(nullable=False)
