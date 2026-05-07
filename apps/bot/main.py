"""Точка входа Telegram-бота CustDevAI (FR-BOT-*; FR-API-03).

Режим выбирается на старте по конфигурации:
  * dev (ENVIRONMENT=development или TELEGRAM_WEBHOOK_URL пустой)
    → long-polling: dp.start_polling(bot).
  * prod (production + TELEGRAM_WEBHOOK_URL задан) → webhook: бот
    регистрирует webhook у Telegram и ждёт update-ов из FastAPI-роутера
    через очередь Redis (apps/api/routers/webhook.py пушит, бот pop-ит).
    Реализация webhook-listener-а — Phase 5 (нагрузочный тюнинг);
    в Phase 2 production-ветка регистрирует webhook и спит, пока
    FastAPI напрямую не feed_update-ит dispatcher (одноинстанный режим).
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from apps.api.config import get_settings
from apps.bot.dispatcher import build_dispatcher, build_redis_storage

logger = logging.getLogger(__name__)


async def _run() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN не задан, бот не запустится")
        return

    storage = build_redis_storage(settings.effective_redis_url)
    dp = build_dispatcher(storage=storage)
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    if settings.is_production and settings.telegram_webhook_url:
        # Регистрируем webhook у Telegram, дальше handler-ы вызываются
        # FastAPI-роутером webhook.py через dp.feed_update(bot, update).
        await bot.set_webhook(
            url=settings.telegram_webhook_url,
            secret_token=settings.telegram_webhook_secret or None,
            drop_pending_updates=False,
        )
        logger.info("[bot] webhook registered: %s", settings.telegram_webhook_url)
        # Контейнер должен оставаться живым — асинхронный idle.
        # FastAPI обрабатывает входящие update-ы независимо.
        stop = asyncio.Event()
        await stop.wait()
    else:
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("[bot] long-polling mode")
        await dp.start_polling(bot)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
