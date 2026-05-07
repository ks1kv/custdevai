"""Push-уведомления исследователю (FR-BOT-09).

В Phase 2 — реальное уведомление по факту завершения последней сессии
кампании: «Все сессии завершены, ML-анализ запустится после Phase 3».
В Phase 3 добавится второе уведомление «Анализ готов, отчёт по ссылке».
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.db.models import Campaign, SessionStatus, User
from apps.api.db.repositories.sessions import InterviewSessionRepository
from apps.bot import messages

logger = logging.getLogger(__name__)


async def maybe_notify_researcher_all_completed(
    db: AsyncSession, *, campaign_id: int
) -> None:
    """Если в кампании больше нет ACTIVE-сессий — отправить push исследователю.

    Граничные случаи:
      - chat_id у исследователя не зарегистрирован → пишем в лог skip,
        не падаем (Phase 4 добавит UI регистрации chat_id).
      - токен notify-бота не задан → используем основной токен
        (settings.telegram_bot_token) — fallback прописан в .env.example.
    """
    sessions = InterviewSessionRepository(db)
    active_left = await sessions.count_active_in_campaign(campaign_id)
    if active_left > 0:
        return

    campaign = await db.get(Campaign, campaign_id)
    if campaign is None or campaign.created_by_user_id is None:
        logger.info("notify skipped: campaign %s has no creator", campaign_id)
        return
    user = await db.get(User, campaign.created_by_user_id)
    if user is None or user.researcher_telegram_chat_id is None:
        logger.info(
            "notify skipped: researcher %s has no telegram chat_id",
            campaign.created_by_user_id,
        )
        return

    completed = await sessions.count_by_status(campaign_id, SessionStatus.COMPLETED)
    interrupted = await sessions.count_by_status(campaign_id, SessionStatus.INTERRUPTED)

    settings = get_settings()
    notify_token = settings.telegram_notify_bot_token or settings.telegram_bot_token
    notify_bot = Bot(notify_token)
    try:
        await notify_bot.send_message(
            chat_id=user.researcher_telegram_chat_id,
            text=messages.RESEARCHER_NOTIFY_ALL_SESSIONS_COMPLETED.format(
                campaign_title=campaign.title,
                campaign_id=campaign.id,
                completed_count=completed,
                interrupted_count=interrupted,
            ),
        )
    except TelegramAPIError as exc:
        # NFR-REL-07: ≤ 1% потерь push допустим, в Phase 5 — retry policy.
        logger.warning("notify delivery failed for campaign %s: %s", campaign_id, exc)
    finally:
        await notify_bot.session.close()
