"""Согласие на обработку данных — callback на inline-кнопку (FR-BOT-01)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from apps.bot import messages
from apps.bot.db import open_session
from apps.bot.keyboards import CONSENT_CALLBACK
from apps.bot.services.consent_service import record_consent
from apps.bot.services.interview_service import format_question
from apps.bot.services.session_service import (
    begin_session,  # noqa: F401  (для типизации контекста — не нужен здесь, но напоминание)
)
from apps.bot.states import (
    DATA_CAMPAIGN_ID,
    DATA_CONSENT_VERSION,
    DATA_CURRENT_QUESTION_ID,
    DATA_SESSION_ID,
    InterviewState,
)

logger = logging.getLogger(__name__)
router = Router(name="bot.consent")


@router.callback_query(F.data == CONSENT_CALLBACK, InterviewState.AWAITING_CONSENT)
async def handle_consent_yes(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    session_id = data.get(DATA_SESSION_ID)
    campaign_id = data.get(DATA_CAMPAIGN_ID)
    current_question_id = data.get(DATA_CURRENT_QUESTION_ID)
    consent_version = data.get(DATA_CONSENT_VERSION) or messages.CURRENT_CONSENT_VERSION
    if session_id is None or campaign_id is None or current_question_id is None:
        await callback.answer("Сессия не найдена. Откройте ссылку заново.", show_alert=True)
        await state.clear()
        return

    async with open_session() as db:
        await record_consent(
            db,
            session_id=int(session_id),
            consent_version=str(consent_version),
        )
        # подгружаем сценарий + вопросы для рендера первого вопроса
        from apps.api.db.repositories.sessions import fetch_campaign_script_questions

        fetched = await fetch_campaign_script_questions(db, int(campaign_id))
        if fetched is None:
            await callback.answer("Кампания недоступна.", show_alert=True)
            await state.clear()
            return
        _, script = fetched
        questions = list(script.questions)

    # Перевод в IN_INTERVIEW + отправка первого вопроса.
    await state.set_state(InterviewState.IN_INTERVIEW)

    # progress_count в момент согласия = 0; current_question_id уже сохранён
    # /start-handler-ом. Сверяемся по id, чтобы переотрисовать корректный вопрос.
    target = next((q for q in questions if q.id == int(current_question_id)), None)
    if target is None:
        target = questions[0]
    index = questions.index(target)

    if isinstance(callback.message, Message):
        # Убираем inline-клавиатуру у предыдущего сообщения.
        # contextlib.suppress: edit может фейлиться по разным причинам
        # (сообщение уже редактировалось, message_id устарел) — это не критично.
        import contextlib

        with contextlib.suppress(Exception):
            await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(format_question(target, index, len(questions)))
    await callback.answer()


@router.message(InterviewState.AWAITING_CONSENT)
async def handle_message_before_consent(message: Message) -> None:
    """Любое текстовое сообщение до согласия — напоминаем нажать кнопку."""
    await message.answer(messages.CONSENT_REQUIRED_REMINDER)
