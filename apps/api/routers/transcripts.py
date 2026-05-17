"""Transcripts API — выдача сессий с полнотекстовым поиском (FR-WEB-05).

Замещает заглушку «Раздел будет доступен после публикации эндпоинта
/transcripts» из вкладок CampaignDetailPage. Поиск идёт через pg_trgm
оператор `%%` (similarity > 0.3) по answers.text — индекс
`ix_answers_text_trgm` добавлен в alembic 0005.

В SQLite-тестах pg_trgm недоступен; pattern-search фоллбэк через ILIKE.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from apps.api.auth.rbac import Role
from apps.api.db.models import (
    Answer,
    InterviewSession,
    Question,
    SentimentLabel,
    SentimentResult,
)
from apps.api.db.repositories.campaigns import CampaignRepository
from apps.api.deps import CurrentUser, DBSession, require_roles
from apps.api.errors import NotFound
from apps.api.reports.pseudonyms import session_to_pseudonym
from apps.api.schemas.pagination import Page, PaginationParams, pagination_dependency
from apps.api.schemas.transcripts import TranscriptAnswerOut, TranscriptSessionOut

router = APIRouter(prefix="/campaigns/{campaign_id}/transcripts", tags=["transcripts"])

_reader = require_roles(Role.RESEARCHER, Role.ANALYST, Role.ADMIN)


def _owner_filter(actor: CurrentUser) -> int | None:
    if Role.ADMIN.value in actor.roles or Role.ANALYST.value in actor.roles:
        return None
    return actor.id


def _dialect_name(session) -> str:  # type: ignore[no-untyped-def]
    """Имя SQL-диалекта подключения (postgresql / sqlite / ...)."""
    return session.bind.dialect.name if session.bind else session.get_bind().dialect.name


@router.get(
    "",
    response_model=Page[TranscriptSessionOut],
    summary="Транскрипты сессий с поиском и фильтром по тональности (FR-WEB-05)",
)
async def list_transcripts(
    campaign_id: int,
    session: DBSession,
    q: str | None = Query(None, min_length=1, max_length=200, description="Полнотекстовый поиск"),
    sentiment: SentimentLabel | None = Query(None, description="Фильтр по метке тональности"),
    pagination: PaginationParams = Depends(pagination_dependency),
    actor: CurrentUser = Depends(_reader),
) -> Page[TranscriptSessionOut]:
    """Список транскриптов кампании.

    Researcher видит только свои кампании; Analyst и Admin — все.
    `q` ищет по тексту ответа через pg_trgm (на Postgres) либо ILIKE.
    `sentiment` фильтрует сессии, у которых есть хотя бы один ответ с
    заданной меткой тональности.
    """
    pagination.validated()
    campaigns_repo = CampaignRepository(session)
    campaign = await campaigns_repo.get(campaign_id)
    owner_id = _owner_filter(actor)
    if campaign is None or (owner_id is not None and campaign.created_by_user_id != owner_id):
        raise NotFound("Кампания не найдена.")

    # Подзапрос session_id-ов, попавших под фильтры.
    base = select(InterviewSession.id).where(InterviewSession.campaign_id == campaign_id)
    if q or sentiment is not None:
        base = base.join(Answer, Answer.session_id == InterviewSession.id)
        if sentiment is not None:
            base = base.join(SentimentResult, SentimentResult.answer_id == Answer.id).where(
                SentimentResult.label == sentiment
            )
        if q:
            if _dialect_name(session) == "postgresql":
                # pg_trgm similarity > threshold (0.3 default). Использует
                # GIN-индекс ix_answers_text_trgm из миграции 0005.
                base = base.where(Answer.text.op("%")(q))
            else:
                # SQLite ILIKE/LIKE case-insensitive только для ASCII.
                # Для кириллицы — приводим обе стороны к lower() через SQL.
                base = base.where(func.lower(Answer.text).contains(q.lower()))
    base = base.distinct()

    # Считаем total.
    total_stmt = select(InterviewSession.id).where(InterviewSession.id.in_(base.scalar_subquery()))
    total_rows = (await session.execute(total_stmt)).scalars().all()
    total = len(total_rows)

    # Загружаем сессии страницы со связанными answers.
    page_ids_stmt = (
        select(InterviewSession.id)
        .where(InterviewSession.id.in_(base.scalar_subquery()))
        .order_by(InterviewSession.id)
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    page_ids = list((await session.execute(page_ids_stmt)).scalars())

    if not page_ids:
        return Page[TranscriptSessionOut](
            items=[], total=total, limit=pagination.limit, offset=pagination.offset
        )

    sessions_stmt = (
        select(InterviewSession)
        .where(InterviewSession.id.in_(page_ids))
        .order_by(InterviewSession.id)
    )
    sessions = list((await session.execute(sessions_stmt)).scalars())

    # Загружаем answers всех сессий страницы одним запросом.
    answers_stmt = select(Answer).where(Answer.session_id.in_(page_ids))
    all_answers = list((await session.execute(answers_stmt)).scalars())
    answers_by_session: dict[int, list[Answer]] = {}
    for a in all_answers:
        answers_by_session.setdefault(a.session_id, []).append(a)

    answer_ids = [a.id for a in all_answers]
    sentiments_map: dict[int, SentimentResult] = {}
    if answer_ids:
        sr_rows = (
            await session.execute(
                select(SentimentResult).where(SentimentResult.answer_id.in_(answer_ids))
            )
        ).scalars()
        sentiments_map = {sr.answer_id: sr for sr in sr_rows}

    question_ids = {a.question_id for a in all_answers}
    questions_map: dict[int, Question] = {}
    if question_ids:
        q_rows = (
            await session.execute(select(Question).where(Question.id.in_(question_ids)))
        ).scalars()
        questions_map = {q_.id: q_ for q_ in q_rows}

    items = [
        _session_to_dto(s, answers_by_session.get(s.id, []), questions_map, sentiments_map)
        for s in sessions
    ]
    return Page[TranscriptSessionOut](
        items=items, total=total, limit=pagination.limit, offset=pagination.offset
    )


def _session_to_dto(
    s: InterviewSession,
    answers: Sequence[Answer],
    questions_map: dict[int, Question],
    sentiments_map: dict[int, SentimentResult],
) -> TranscriptSessionOut:
    sorted_answers = sorted(
        answers,
        key=lambda a: (
            questions_map[a.question_id].order_index if a.question_id in questions_map else 0
        ),
    )
    answers_dto: list[TranscriptAnswerOut] = []
    for a in sorted_answers:
        q = questions_map.get(a.question_id)
        sr = sentiments_map.get(a.id)
        answers_dto.append(
            TranscriptAnswerOut(
                question_id=a.question_id,
                question_order=q.order_index if q else 0,
                question_text=q.text if q else "",
                answer_text=a.text,
                answered_at=a.answered_at,
                sentiment_label=sr.label if sr else None,
                sentiment_confidence=float(sr.confidence) if sr else None,
            )
        )
    return TranscriptSessionOut(
        session_id=s.id,
        pseudonym=session_to_pseudonym(s.telegram_id_hash),
        status=s.status,
        started_at=s.started_at,
        completed_at=s.completed_at,
        answers=answers_dto,
    )
