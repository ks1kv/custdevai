"""Репозиторий сессий интервью."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models import Campaign, InterviewSession, Script, SessionStatus


class InterviewSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, session_id: int) -> InterviewSession | None:
        return await self._session.get(InterviewSession, session_id)

    async def get_by_telegram_hash(
        self, *, campaign_id: int, telegram_id_hash: bytes
    ) -> InterviewSession | None:
        """Найти сессию для пары (campaign, hash) — для resume и идемпотентного
        /start (UNIQUE из миграции 0001 sessions(campaign_id, telegram_id_hash))."""
        stmt = select(InterviewSession).where(
            InterviewSession.campaign_id == campaign_id,
            InterviewSession.telegram_id_hash == telegram_id_hash,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        campaign_id: int,
        telegram_id_hash: bytes,
        now: datetime,
    ) -> InterviewSession:
        session = InterviewSession(
            campaign_id=campaign_id,
            telegram_id_hash=telegram_id_hash,
            status=SessionStatus.ACTIVE,
            progress_count=0,
            started_at=now,
            last_activity_at=now,
        )
        self._session.add(session)
        await self._session.flush()
        return session

    async def count_active_in_campaign(self, campaign_id: int) -> int:
        """Сколько сессий ещё в ACTIVE — нужно для FR-BOT-09."""
        stmt = select(func.count()).where(
            InterviewSession.campaign_id == campaign_id,
            InterviewSession.status == SessionStatus.ACTIVE,
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_by_status(self, campaign_id: int, status: SessionStatus) -> int:
        stmt = select(func.count()).where(
            InterviewSession.campaign_id == campaign_id,
            InterviewSession.status == status,
        )
        return int((await self._session.execute(stmt)).scalar_one())


async def fetch_campaign_script_questions(
    db: AsyncSession, campaign_id: int
) -> tuple[Campaign, Script] | None:
    """Загрузить кампанию + сценарий c вопросами (вопросы — selectin lazy в Script).

    Возвращает None, если кампания не существует.
    """
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        return None
    script = await db.get(Script, campaign.script_id)
    if script is None:
        return None
    # Триггерим загрузку questions через relationship (lazy=selectin в модели Script).
    await db.refresh(script, attribute_names=["questions"])
    return campaign, script
