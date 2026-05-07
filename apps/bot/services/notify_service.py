"""Push-уведомления исследователю (FR-BOT-09).

Phase 2 — первый push «все сессии завершены, ML-анализ запущен».
Phase 3 — второй push «ML-анализ завершён» через notify_researcher_analysis_ready.
Также Phase 3 enqueue-ит analyze_campaign(campaign_id) сразу после первого
push, что закрывает FR-BOT-09 полностью.
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


async def maybe_notify_researcher_all_completed(db: AsyncSession, *, campaign_id: int) -> None:
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

    # Phase 3 — после первого push сразу ставим ML-пайплайн в очередь.
    # FR-API-04: автоматический запуск анализа на событии завершения кампании.
    try:
        from apps.worker.tasks.ml_pipeline import analyze_campaign

        analyze_campaign.delay(campaign_id)
        logger.info("ml_pipeline_enqueued", extra={"campaign_id": campaign_id})
    except Exception:
        # Если Celery недоступен (например, в тестах без брокера и без
        # always_eager), мягко логируем без фатала — аналитик может
        # запустить вручную через POST /api/v1/campaigns/{id}/analyze.
        logger.exception("ml_pipeline enqueue failed for campaign %s", campaign_id)


async def notify_researcher_analysis_ready(
    db: AsyncSession,
    *,
    campaign_id: int,
    topics_count: int,
    sentiment_inserted: int,
) -> None:
    """Phase 3 / FR-BOT-09 закрытие: второй push «ML-анализ завершён»."""
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None or campaign.created_by_user_id is None:
        return
    user = await db.get(User, campaign.created_by_user_id)
    if user is None or user.researcher_telegram_chat_id is None:
        logger.info(
            "analysis_notify skipped: researcher %s has no telegram chat_id",
            campaign.created_by_user_id,
        )
        return

    settings = get_settings()
    notify_token = settings.telegram_notify_bot_token or settings.telegram_bot_token
    if not notify_token:
        return
    notify_bot = Bot(notify_token)
    try:
        await notify_bot.send_message(
            chat_id=user.researcher_telegram_chat_id,
            text=messages.RESEARCHER_NOTIFY_ANALYSIS_READY.format(
                campaign_title=campaign.title,
                campaign_id=campaign.id,
                topics_count=topics_count,
                sentiment_inserted=sentiment_inserted,
            ),
        )
    except TelegramAPIError as exc:
        logger.warning("analysis_notify delivery failed for campaign %s: %s", campaign_id, exc)
    finally:
        await notify_bot.session.close()
