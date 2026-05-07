"""Создание и переходы статусов InterviewSession (FR-BOT-01, 06, 07, 10, FR-DB-03)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.hashing import hash_telegram_id
from apps.api.db.models import (
    Campaign,
    InterviewSession,
    Question,
    Script,
    SessionStatus,
)
from apps.api.db.repositories.campaigns import CampaignRepository
from apps.api.db.repositories.sessions import (
    InterviewSessionRepository,
    fetch_campaign_script_questions,
)


@dataclass(frozen=True)
class StartContext:
    """Что нужно бот-handler-у после открытия /start."""

    session: InterviewSession
    campaign: Campaign
    script: Script
    questions: list[Question]
    is_new_session: bool
    is_completed: bool


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


async def begin_session(
    db: AsyncSession, *, campaign_id: int, telegram_user_id: int
) -> StartContext | None:
    """Открыть или возобновить сессию интервью.

    Возвращает None, если кампания не RUNNING (бот покажет «опрос недоступен»).
    Для уже existing-сессии:
      - active → resume (продолжить с текущего вопроса);
      - completed → флаг is_completed=True (бот покажет «вы уже прошли»);
      - interrupted → создать НОВУЮ сессию через UNIQUE-конфликт нельзя,
        поэтому возвращаем существующую с is_completed=True (не возобновляем
        прерванное, чтобы избежать смешения старых и новых ответов).
    """
    campaigns = CampaignRepository(db)
    campaign = await campaigns.get_running_for_invitation(campaign_id)
    if campaign is None:
        return None

    fetched = await fetch_campaign_script_questions(db, campaign_id)
    if fetched is None:
        return None
    campaign, script = fetched
    questions = list(script.questions)
    if not questions:
        return None  # сценарий без вопросов — некорректное состояние

    telegram_hash = hash_telegram_id(telegram_user_id, bytes(campaign.pseudonym_salt))
    sessions = InterviewSessionRepository(db)
    existing = await sessions.get_by_telegram_hash(
        campaign_id=campaign_id, telegram_id_hash=telegram_hash
    )
    if existing is not None:
        if existing.status == SessionStatus.ACTIVE:
            existing.last_activity_at = _utcnow()
            await db.commit()
            return StartContext(
                session=existing,
                campaign=campaign,
                script=script,
                questions=questions,
                is_new_session=False,
                is_completed=False,
            )
        # completed | interrupted — повторное участие не предусмотрено
        return StartContext(
            session=existing,
            campaign=campaign,
            script=script,
            questions=questions,
            is_new_session=False,
            is_completed=True,
        )

    new_session = await sessions.create(
        campaign_id=campaign_id,
        telegram_id_hash=telegram_hash,
        now=_utcnow(),
    )
    await db.commit()
    return StartContext(
        session=new_session,
        campaign=campaign,
        script=script,
        questions=questions,
        is_new_session=True,
        is_completed=False,
    )


async def mark_interrupted(db: AsyncSession, session_id: int) -> None:
    """`/stop` — закрыть сессию как INTERRUPTED, ответы НЕ удаляем (FR-BOT-06)."""
    session = await db.get(InterviewSession, session_id)
    if session is None or session.status != SessionStatus.ACTIVE:
        return
    session.status = SessionStatus.INTERRUPTED
    session.last_activity_at = _utcnow()
    await db.commit()


async def mark_completed(db: AsyncSession, session_id: int) -> None:
    """Закрыть сессию как COMPLETED после ответа на последний вопрос (FR-BOT-07)."""
    session = await db.get(InterviewSession, session_id)
    if session is None:
        return
    now = _utcnow()
    session.status = SessionStatus.COMPLETED
    session.completed_at = now
    session.last_activity_at = now
    await db.commit()
