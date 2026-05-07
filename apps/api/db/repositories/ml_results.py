"""Репозитории для записи результатов ML-пайплайна (FR-RPT-07).

Каждый репозиторий реализует «стереть существующие результаты для
кампании, потом вставить новые» в одной транзакции — это нужно для
повторного запуска анализа (FR-RPT-07) без накопления дублей.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models import (
    Answer,
    InterviewSession,
    SentimentLabel,
    SentimentResult,
    SessionTopic,
    Topic,
)
from apps.ml.sentiment.schemas import SentimentInference
from apps.ml.topics.schemas import TopicModelingResult


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


async def fetch_campaign_answer_corpus(
    db: AsyncSession, campaign_id: int
) -> tuple[list[Answer], list[InterviewSession]]:
    """Загрузить все ответы и сессии кампании для пайплайна анализа."""
    answers_stmt = (
        select(Answer)
        .join(InterviewSession, InterviewSession.id == Answer.session_id)
        .where(InterviewSession.campaign_id == campaign_id)
        .order_by(Answer.session_id, Answer.question_id)
    )
    answers = list((await db.execute(answers_stmt)).scalars().all())

    sessions_stmt = select(InterviewSession).where(
        InterviewSession.campaign_id == campaign_id
    )
    sessions = list((await db.execute(sessions_stmt)).scalars().all())
    return answers, sessions


class SentimentResultRepository:
    """DELETE+INSERT для FR-RPT-07."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_campaign(
        self,
        campaign_id: int,
        *,
        answers: Sequence[Answer],
        inferences: Sequence[SentimentInference],
    ) -> int:
        """Удалить старые sentiment_results всех ответов кампании, вставить
        новые в одной транзакции. Возвращает число записанных строк
        (не считая помеченных is_language_error — для них пропуск).
        """
        if len(answers) != len(inferences):
            raise ValueError("answers и inferences должны быть параллельными списками")

        answer_ids = [a.id for a in answers]
        if answer_ids:
            await self._session.execute(
                delete(SentimentResult).where(
                    SentimentResult.answer_id.in_(answer_ids)
                )
            )

        now = _utcnow()
        inserted = 0
        for answer, inf in zip(answers, inferences, strict=True):
            if inf.is_language_error:
                # FR-SENT-06: не-русский текст не классифицируется и не
                # подсчитывается в агрегированной статистике.
                continue
            self._session.add(
                SentimentResult(
                    answer_id=answer.id,
                    label=inf.label,
                    confidence=float(inf.confidence),
                    analyzed_at=now,
                )
            )
            inserted += 1
        await self._session.flush()
        return inserted


class TopicResultRepository:
    """DELETE+INSERT для тем и связей session_topics (FR-RPT-07)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_campaign(
        self,
        campaign_id: int,
        result: TopicModelingResult,
    ) -> dict[int, int]:
        """Удалить старые темы кампании (CASCADE удаляет session_topics),
        вставить новые. Возвращает словарь model_topic_id → db_topic_id для
        последующей привязки session_topics.
        """
        await self._session.execute(
            delete(Topic).where(Topic.campaign_id == campaign_id)
        )
        await self._session.flush()

        # INSERT topics
        topic_id_map: dict[int, int] = {}
        for tr in result.topics:
            t = Topic(
                campaign_id=campaign_id,
                topic_id_in_model=tr.topic_id_in_model,
                label=tr.label,
                keywords=list(tr.keywords),
                frequency_count=tr.frequency_count,
                is_noise=tr.is_noise,
            )
            self._session.add(t)
            await self._session.flush()
            topic_id_map[tr.topic_id_in_model] = t.id

        # INSERT session_topics с representative_quote — для top-3 ассоциаций
        # representative_quote уже задан в SessionTopicAssignment, для остальных
        # None.
        for assignment in result.assignments:
            db_topic_id = topic_id_map.get(assignment.topic_id_in_model)
            if db_topic_id is None:
                continue
            self._session.add(
                SessionTopic(
                    session_id=assignment.session_id,
                    topic_id=db_topic_id,
                    representative_quote=assignment.representative_quote,
                )
            )
        await self._session.flush()
        return topic_id_map


# Явный реэкспорт SentimentLabel для удобства импорта потребителей.
__all__ = [
    "SentimentLabel",
    "SentimentResultRepository",
    "TopicResultRepository",
    "fetch_campaign_answer_corpus",
]
