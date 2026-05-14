"""Sessions sweeper — Celery periodic-таск (FR-BOT-05).

После 48 часов неактивности (по умолчанию; настраивается через
SESSION_INACTIVE_HOURS) сессия должна перейти из ACTIVE в INTERRUPTED.
Phase 2 заложил Redis FSM TTL на 48 часов, но статус в БД оставался
ACTIVE — это занижало аналитику завершённости кампаний и блокировало
FR-RPT-07 (повторный анализ при добавлении сессий).

Phase 5 закрывает gap: Celery beat запускает таск каждые 15 минут.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.config import get_settings
from apps.api.db.models import InterviewSession, SessionStatus
from apps.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="sessions.sweep_inactive")
def sweep_inactive_sessions() -> dict:
    """Закрыть зависшие active-сессии (FR-BOT-05).

    Returns:
        dict с полями `swept` (число переведённых сессий) и `cutoff`
        (ISO-таймштамп границы неактивности).
    """
    settings = get_settings()
    return asyncio.run(
        _run_with_own_session(settings.effective_database_url, settings.session_inactive_hours)
    )


async def _run_with_own_session(database_url: str, inactive_hours: int) -> dict:
    """Создать собственный engine и выполнить sweep. Celery-обёртка."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as db:
            result = await sweep_inactive(db, inactive_hours=inactive_hours)
        return result
    finally:
        await engine.dispose()


async def sweep_inactive(db: AsyncSession, *, inactive_hours: int) -> dict:
    """Перевести зависшие active-сессии в interrupted.

    Эта функция принимает готовую сессию и пригодна для unit/integration
    тестирования (см. tests/integration/test_sessions_sweeper.py).
    """
    # last_activity_at в схеме — TIMESTAMP without TZ; cutoff приводим к naive UTC.
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=inactive_hours)
    cutoff_naive = cutoff.replace(tzinfo=None)
    result = await db.execute(
        update(InterviewSession)
        .where(InterviewSession.status == SessionStatus.ACTIVE)
        .where(InterviewSession.last_activity_at < cutoff_naive)
        .values(status=SessionStatus.INTERRUPTED)
    )
    await db.commit()
    count = result.rowcount or 0
    logger.info(
        "sessions_sweeper_ran",
        extra={"swept": count, "cutoff": cutoff_naive.isoformat()},
    )
    return {"swept": count, "cutoff": cutoff_naive.isoformat()}
