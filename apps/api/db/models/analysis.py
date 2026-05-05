"""Модели Topic, SessionTopic, SentimentResult."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db.base import Base, TimestampMixin


class SentimentLabel(str, enum.Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    LOW_CONFIDENCE = "low_confidence"


class Topic(Base, TimestampMixin):
    """Тема, извлечённая BERTopic-ом для конкретной кампании."""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_id_in_model: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    frequency_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    is_noise: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SessionTopic(Base):
    """M:N связь сессии и темы. Composite PK гарантирует уникальность пары."""

    __tablename__ = "session_topics"

    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("topics.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    representative_quote: Mapped[str | None] = mapped_column(Text, nullable=True)


class SentimentResult(Base, TimestampMixin):
    """Результат тонального анализа конкретного ответа (FR-SENT-*)."""

    __tablename__ = "sentiment_results"
    __table_args__ = (Index("ix_sentiment_answer_label", "answer_id", "label"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    answer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("answers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    label: Mapped[SentimentLabel] = mapped_column(
        Enum(SentimentLabel, name="sentiment_label", create_constraint=True),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(nullable=False)
