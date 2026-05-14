"""Telegram Bot webhook (FR-API-03).

В production Telegram шлёт update-ы на этот эндпойнт. Эндпойнт:
  1. валидирует X-Telegram-Bot-Api-Secret-Token против
     settings.telegram_webhook_secret (NFR-SEC-06);
  2. парсит JSON в aiogram.types.Update;
  3. форвардит в dispatcher через dp.feed_update(bot, update).

Bot и Dispatcher создаются как singleton при первом запросе и
переиспользуются. В dev этот эндпойнт можно не задевать — long-polling
обрабатывает update-ы внутри bot-контейнера.
"""

from __future__ import annotations

import logging
from typing import Annotated

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import APIRouter, Header, status

from apps.api.config import Settings
from apps.api.deps import SettingsDep
from apps.api.errors import AuthenticationFailed, ValidationFailed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])

_BOT: Bot | None = None
_DP: Dispatcher | None = None


def _get_bot_and_dispatcher(settings: Settings) -> tuple[Bot, Dispatcher]:
    """Lazy-init: при первом запросе строим Bot + Dispatcher."""
    global _BOT, _DP
    if _BOT is None or _DP is None:
        if not settings.telegram_bot_token:
            raise ValidationFailed("TELEGRAM_BOT_TOKEN не задан, webhook отключён.")
        from apps.bot.dispatcher import build_dispatcher, build_redis_storage

        _BOT = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        _DP = build_dispatcher(storage=build_redis_storage(settings.effective_redis_url))
    return _BOT, _DP


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Telegram Bot API webhook",
    # Тяжёлая Update-схема aiogram не попадает в публичный OpenAPI,
    # чтобы не раздувать /api/openapi.json (sub-app pattern, SHOULD-9
    # Phase 5). Бот всё равно вызывается напрямую Telegram API, не SPA.
    include_in_schema=False,
)
async def telegram_webhook(
    update: Update,
    settings: SettingsDep,
    x_telegram_bot_api_secret_token: Annotated[
        str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")
    ] = None,
) -> dict[str, str]:
    """Принимает типизированный Update; валидирует секрет и форвардит в dispatcher."""
    expected = settings.telegram_webhook_secret
    if expected and x_telegram_bot_api_secret_token != expected:
        raise AuthenticationFailed("Невалидный webhook-secret.")

    bot, dp = _get_bot_and_dispatcher(settings)
    try:
        await dp.feed_update(bot, update)
    except Exception as exc:
        logger.exception("webhook handler failed: %s", exc)
        # Telegram повторит доставку при non-200 → отдаём 200 даже при
        # внутренней ошибке (FR-API-08 идемпотентность защитит от дубля).
    return {"status": "ok"}
