"""DTO для GET /transcripts (FR-WEB-05)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from apps.api.db.models import SentimentLabel, SessionStatus


class TranscriptAnswerOut(BaseModel):
    """Один ответ в транскрипте.

    Q/A/timestamp/pseudonym FR-WEB-05 + sentiment-фильтр через outerjoin.
    """

    model_config = ConfigDict(from_attributes=True)

    question_id: int
    question_order: int
    question_text: str
    answer_text: str
    answered_at: datetime
    sentiment_label: SentimentLabel | None = None
    sentiment_confidence: float | None = None


class TranscriptSessionOut(BaseModel):
    """Транскрипт одной сессии."""

    model_config = ConfigDict(from_attributes=True)

    session_id: int
    pseudonym: str
    status: SessionStatus
    started_at: datetime | None
    completed_at: datetime | None
    answers: list[TranscriptAnswerOut]
