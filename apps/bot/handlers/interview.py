"""Сбор ответов: основное состояние диалога (FR-BOT-02, 03, 06, 07, 08; FR-DB-02; FR-API-08)."""

from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from apps.api.db.models import Question
from apps.api.db.models.campaign import CampaignStatus
from apps.bot import messages
from apps.bot.db import open_session
from apps.bot.keyboards import LONG_ANSWER_DONE_CALLBACK, long_answer_done_keyboard
from apps.bot.services.interview_service import (
    MAX_ANSWER_LENGTH,
    accept_answer,
    format_question,
)
from apps.bot.services.notify_service import maybe_notify_researcher_all_completed
from apps.bot.services.session_service import mark_completed, mark_interrupted
from apps.bot.states import (
    DATA_CAMPAIGN_ID,
    DATA_CURRENT_QUESTION_ID,
    DATA_PENDING_CHUNKS,
    DATA_SESSION_ID,
    InterviewState,
)

logger = logging.getLogger(__name__)
router = Router(name="bot.interview")

# FR-SENT-06: поддерживается только русский. На уровне бота отбраковываем
# тексты без хотя бы одного кириллического символа — чтобы латиница/эмодзи
# не доходили до ML, который их всё равно отвергнет.
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def _has_cyrillic(text: str) -> bool:
    return _CYRILLIC_RE.search(text) is not None


# ---- /stop ------------------------------------------------------------------


@router.message(Command("stop"))
async def handle_stop(message: Message, state: FSMContext) -> None:
    """FR-BOT-06: из любого состояния — закрыть сессию как INTERRUPTED.

    Все ранее данные ответы сохраняются (NOT удаляются — caskade в БД
    отрабатывает только при удалении самой сессии, а мы её не удаляем).
    """
    data = await state.get_data()
    session_id = data.get(DATA_SESSION_ID)
    campaign_id = data.get(DATA_CAMPAIGN_ID)
    if session_id is not None:
        async with open_session() as db:
            await mark_interrupted(db, int(session_id))
            if campaign_id is not None:
                await maybe_notify_researcher_all_completed(db, campaign_id=int(campaign_id))
    await state.clear()
    await message.answer(messages.INTERRUPTED_MESSAGE)


# ---- Текстовый ответ в IN_INTERVIEW -----------------------------------------


@router.message(InterviewState.IN_INTERVIEW, F.text)
async def handle_answer(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer(messages.NON_TEXT_REJECTED)
        return

    if not _has_cyrillic(text):
        await message.answer(messages.NON_CYRILLIC_REJECTED)
        return

    if len(text) >= MAX_ANSWER_LENGTH:
        # Telegram сам режет на 4096; пользователь, скорее всего, попытается
        # прислать ответ длиннее лимита одного сообщения. Переходим в режим
        # склейки чанков (FR-BOT-08).
        await state.update_data({DATA_PENDING_CHUNKS: [text]})
        await state.set_state(InterviewState.IN_INTERVIEW_LONG_ANSWER)
        await message.answer(messages.ANSWER_TOO_LONG, reply_markup=long_answer_done_keyboard())
        return

    await _persist_and_advance(message, state, text)


async def _persist_and_advance(message: Message, state: FSMContext, text: str) -> None:
    """Сохранить ответ, уйти к следующему вопросу или закрыть сессию."""
    data = await state.get_data()
    session_id = int(data[DATA_SESSION_ID])
    campaign_id = int(data[DATA_CAMPAIGN_ID])
    question_id = int(data[DATA_CURRENT_QUESTION_ID])

    async with open_session() as db:
        from apps.api.db.repositories.sessions import fetch_campaign_script_questions

        fetched = await fetch_campaign_script_questions(db, campaign_id)
        if fetched is None:
            await message.answer(messages.INTERNAL_ERROR)
            return
        campaign_obj, script = fetched

        # Жёсткая семантика паузы/завершения: ответы принимаем только для
        # RUNNING. На паузе сессия остаётся открытой — респондент сможет
        # продолжить после Resume, ранее сохранённые ответы не теряются.
        if campaign_obj.status == CampaignStatus.PAUSED:
            await message.answer(messages.CAMPAIGN_PAUSED_REJECT)
            return
        if campaign_obj.status == CampaignStatus.COMPLETED:
            await message.answer(messages.CAMPAIGN_COMPLETED_REJECT)
            await state.clear()
            return
        if campaign_obj.status != CampaignStatus.RUNNING:
            # draft не должен встречаться в активной сессии, но safe-guard.
            await message.answer(messages.CAMPAIGN_PAUSED_REJECT)
            return

        questions: list[Question] = list(script.questions)

        try:
            result = await accept_answer(
                db,
                session_id=session_id,
                question_id=question_id,
                text=text,
                questions=questions,
            )
        except Exception as exc:
            logger.exception("accept_answer failed: %s", exc)
            await message.answer(messages.INTERNAL_ERROR)
            return

        if result.is_last:
            await mark_completed(db, session_id)
            await maybe_notify_researcher_all_completed(db, campaign_id=campaign_id)

    # Подтверждение (только после commit-а в accept_answer).
    if not result.is_last and result.next_question is not None:
        index = next((i for i, q in enumerate(questions) if q.id == result.next_question.id), 0)
        await state.update_data({DATA_CURRENT_QUESTION_ID: result.next_question.id})
        await message.answer(messages.ANSWER_ACCEPTED_SHORT)
        await message.answer(format_question(result.next_question, index, len(questions)))
    else:
        await message.answer(messages.COMPLETED_MESSAGE)
        await state.clear()


# ---- Длинный ответ: накопление чанков ---------------------------------------


@router.message(InterviewState.IN_INTERVIEW_LONG_ANSWER, F.text)
async def handle_long_answer_chunk(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    data = await state.get_data()
    chunks: list[str] = list(data.get(DATA_PENDING_CHUNKS) or [])
    chunks.append(text)
    await state.update_data({DATA_PENDING_CHUNKS: chunks})
    await message.answer(
        messages.LONG_ANSWER_CHUNK_ACCEPTED, reply_markup=long_answer_done_keyboard()
    )


@router.callback_query(F.data == LONG_ANSWER_DONE_CALLBACK, InterviewState.IN_INTERVIEW_LONG_ANSWER)
async def handle_long_answer_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    chunks: list[str] = list(data.get(DATA_PENDING_CHUNKS) or [])
    if not chunks:
        await callback.answer("Не получено ни одной части ответа.", show_alert=True)
        return
    full_text = "\n".join(chunks)
    if isinstance(callback.message, Message):
        import contextlib

        with contextlib.suppress(Exception):
            await callback.message.edit_reply_markup(reply_markup=None)
        # очищаем чанки и возвращаемся в IN_INTERVIEW
        await state.update_data({DATA_PENDING_CHUNKS: []})
        await state.set_state(InterviewState.IN_INTERVIEW)
        await _persist_and_advance(callback.message, state, full_text)
    await callback.answer()


# ---- Non-text fallback в IN_INTERVIEW ---------------------------------------


@router.message(InterviewState.IN_INTERVIEW)
@router.message(InterviewState.IN_INTERVIEW_LONG_ANSWER)
async def handle_non_text_in_interview(message: Message) -> None:
    """FR-BOT-04: в активном интервью non-text → отказ, состояние не меняется."""
    await message.answer(messages.NON_TEXT_REJECTED)
