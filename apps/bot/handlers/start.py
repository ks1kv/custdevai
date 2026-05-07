"""/start <deep_link_payload> — создание или возобновление сессии (FR-BOT-01, 10)."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from apps.bot import messages
from apps.bot.db import open_session
from apps.bot.deeplink import InvalidDeepLink, parse_campaign_id
from apps.bot.keyboards import consent_keyboard
from apps.bot.services.session_service import begin_session
from apps.bot.states import (
    DATA_CAMPAIGN_ID,
    DATA_CONSENT_VERSION,
    DATA_CURRENT_QUESTION_ID,
    DATA_SESSION_ID,
    InterviewState,
)

logger = logging.getLogger(__name__)
router = Router(name="bot.start")


@router.message(CommandStart())
async def handle_start(message: Message, command: CommandObject, state: FSMContext) -> None:
    """`/start c<campaign_id>` — единственная точка входа в интервью.

    На каждом шаге сообщения и состояния идут на русском (CLAUDE.md §4).
    Telegram ID пользователя нигде не пишем — только хеш через
    hash_telegram_id() из apps.api.auth.hashing (FR-BOT-10).
    """
    if message.from_user is None:
        return  # service-сообщение без пользователя

    try:
        campaign_id = parse_campaign_id(command.args)
    except InvalidDeepLink:
        await message.answer(messages.INVALID_DEEPLINK)
        return

    async with open_session() as db:
        ctx = await begin_session(
            db, campaign_id=campaign_id, telegram_user_id=message.from_user.id
        )

    if ctx is None:
        await message.answer(messages.CAMPAIGN_NOT_RUNNING)
        return

    if ctx.is_completed:
        await message.answer(messages.ALREADY_COMPLETED)
        await state.clear()
        return

    # Сохраняем контекст диалога в FSM data; current_question_id = id текущего
    # вопроса по progress_count. Для новой сессии — первый вопрос.
    next_index = ctx.session.progress_count
    if next_index >= len(ctx.questions):
        # технически не должно случиться без COMPLETED, но safe-guard
        await message.answer(messages.ALREADY_COMPLETED)
        await state.clear()
        return
    current_q = ctx.questions[next_index]

    await state.set_data(
        {
            DATA_SESSION_ID: ctx.session.id,
            DATA_CAMPAIGN_ID: ctx.campaign.id,
            DATA_CURRENT_QUESTION_ID: current_q.id,
            DATA_CONSENT_VERSION: messages.CURRENT_CONSENT_VERSION,
        }
    )

    if ctx.is_new_session:
        await state.set_state(InterviewState.AWAITING_CONSENT)
        await message.answer(
            messages.CONSENT_TEXT.format(campaign_title=ctx.campaign.title),
            reply_markup=consent_keyboard(),
        )
    else:
        # Resume в существующую active-сессию: согласие уже было дано раньше
        # (хранится в таблице consents Phase 2 ревизии 0002), сразу переходим
        # к текущему вопросу. Дублировать запись Consent не требуется.
        await state.set_state(InterviewState.IN_INTERVIEW)
        from apps.bot.services.interview_service import format_question

        await message.answer(format_question(current_q, next_index, len(ctx.questions)))
