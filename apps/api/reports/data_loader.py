"""Сборка корпуса данных для одного отчёта (FR-RPT-01..08).

`load_campaign_report_context()` — единственная I/O-операция модуля
reports: загружает кампанию + сценарий + вопросы + сессии + ответы +
sentiment_results + темы + связки session_topics в иммутабельный DTO
`CampaignReportContext`. Дальше генераторы PDF/XLSX работают только
с DTO — никаких обращений к БД из render-кода.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.db.models import (
    Answer,
    Campaign,
    InterviewSession,
    Question,
    Script,
    SentimentLabel,
    SentimentResult,
    SessionStatus,
    SessionTopic,
    Topic,
)
from apps.api.errors import NotFound
from apps.api.reports.pseudonyms import session_to_pseudonym


@dataclass(frozen=True)
class AnswerView:
    """Ответ на вопрос с привязкой к сессии и тональностью."""

    answer_id: int
    session_id: int
    pseudonym: str
    question_id: int
    question_text: str
    question_order: int
    text: str
    answered_at: datetime
    sentiment_label: SentimentLabel | None
    sentiment_confidence: float | None


@dataclass(frozen=True)
class SessionView:
    """Сессия с псевдонимом и базовыми полями."""

    session_id: int
    pseudonym: str
    status: SessionStatus
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True)
class TopicView:
    """Тема с keywords, частотой и top-3 цитатами (FR-TOP-02, FR-RPT-05)."""

    topic_id: int
    topic_id_in_model: int
    label: str | None
    keywords: list[str]
    frequency_count: int
    is_noise: bool
    quotes: list[tuple[str, str]]  # [(pseudonym, quote_text), ...]


@dataclass(frozen=True)
class CampaignReportContext:
    """Полный контекст для генерации одного отчёта.

    Иммутабельный — все поля рассчитываются в `load_campaign_report_context()`
    и далее не меняются. Это даёт детерминизм генератора и упрощает
    тестирование с FakeStorage.
    """

    campaign_id: int
    campaign_title: str
    campaign_description: str | None
    script_title: str
    started_at: datetime | None
    completed_at: datetime | None
    target_topic_count: int
    sessions: list[SessionView]
    answers: list[AnswerView]
    sentiment_distribution: dict[SentimentLabel, int]
    topics: list[TopicView]
    generated_at: datetime


async def load_campaign_report_context(
    db: AsyncSession, campaign_id: int, *, generated_at: datetime
) -> CampaignReportContext:
    """Загрузить весь корпус данных одной кампании одним пакетом запросов."""
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise NotFound("Кампания не найдена.")

    script = await db.get(Script, campaign.script_id)
    if script is None:
        raise NotFound("Сценарий кампании не найден.")
    await db.refresh(script, attribute_names=["questions"])

    questions: dict[int, Question] = {q.id: q for q in script.questions}

    sessions_stmt = (
        select(InterviewSession)
        .where(InterviewSession.campaign_id == campaign_id)
        .order_by(InterviewSession.id)
    )
    sessions_orm = list((await db.execute(sessions_stmt)).scalars().all())
    sessions = [
        SessionView(
            session_id=s.id,
            pseudonym=session_to_pseudonym(s.id),
            status=s.status,
            started_at=s.started_at,
            completed_at=s.completed_at,
        )
        for s in sessions_orm
    ]
    pseudonym_by_session: dict[int, str] = {s.session_id: s.pseudonym for s in sessions}

    answers_stmt = (
        select(Answer, SentimentResult)
        .join(
            SentimentResult,
            SentimentResult.answer_id == Answer.id,
            isouter=True,
        )
        .join(InterviewSession, InterviewSession.id == Answer.session_id)
        .where(InterviewSession.campaign_id == campaign_id)
        .order_by(Answer.session_id, Answer.question_id)
    )
    answer_rows = (await db.execute(answers_stmt)).all()

    sentiment_distribution: dict[SentimentLabel, int] = defaultdict(int)
    answers: list[AnswerView] = []
    for answer, sentiment in answer_rows:
        question = questions.get(answer.question_id)
        if question is None:
            continue
        sentiment_label = sentiment.label if sentiment is not None else None
        sentiment_confidence = float(sentiment.confidence) if sentiment is not None else None
        if sentiment_label is not None:
            sentiment_distribution[sentiment_label] += 1
        answers.append(
            AnswerView(
                answer_id=answer.id,
                session_id=answer.session_id,
                pseudonym=pseudonym_by_session.get(
                    answer.session_id, session_to_pseudonym(answer.session_id)
                ),
                question_id=question.id,
                question_text=question.text,
                question_order=question.order_index,
                text=answer.text,
                answered_at=answer.answered_at,
                sentiment_label=sentiment_label,
                sentiment_confidence=sentiment_confidence,
            )
        )

    topics_stmt = (
        select(Topic)
        .where(Topic.campaign_id == campaign_id)
        .options(selectinload(Topic.__mapper__.attrs.get) if False else None)  # placeholder
        .order_by(Topic.is_noise.asc(), Topic.frequency_count.desc())
    )
    # Простой запрос — без selectinload (на SQLite ARRAY-fallback недоступен).
    topics_stmt = (
        select(Topic)
        .where(Topic.campaign_id == campaign_id)
        .order_by(Topic.is_noise.asc(), Topic.frequency_count.desc())
    )
    topics_orm = list((await db.execute(topics_stmt)).scalars().all())

    quotes_by_topic: dict[int, list[tuple[str, str]]] = defaultdict(list)
    if topics_orm:
        topic_ids = [t.id for t in topics_orm]
        st_stmt = (
            select(SessionTopic)
            .where(SessionTopic.topic_id.in_(topic_ids))
            .where(SessionTopic.representative_quote.is_not(None))
        )
        for st in (await db.execute(st_stmt)).scalars().all():
            quote = st.representative_quote
            if quote is None:
                continue
            quotes_by_topic[st.topic_id].append(
                (
                    pseudonym_by_session.get(st.session_id, session_to_pseudonym(st.session_id)),
                    quote,
                )
            )

    topics = [
        TopicView(
            topic_id=t.id,
            topic_id_in_model=t.topic_id_in_model,
            label=t.label,
            keywords=list(t.keywords or []),
            frequency_count=t.frequency_count,
            is_noise=t.is_noise,
            quotes=quotes_by_topic.get(t.id, [])[:3],
        )
        for t in topics_orm
    ]

    return CampaignReportContext(
        campaign_id=campaign.id,
        campaign_title=campaign.title,
        campaign_description=campaign.description,
        script_title=script.title,
        started_at=campaign.started_at,
        completed_at=campaign.completed_at,
        target_topic_count=campaign.target_topic_count,
        sessions=sessions,
        answers=answers,
        sentiment_distribution=dict(sentiment_distribution),
        topics=topics,
        generated_at=generated_at,
    )
