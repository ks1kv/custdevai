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
    AnswerResult,
    accept_answer,
    format_question,
    get_existing_answer_text,
    skip_question,
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


# ---- /back — вернуться к предыдущему вопросу --------------------------------
# Регистрируем ДО handle_answer, как и /skip — F.text иначе перехватит `/back`.


@router.message(InterviewState.IN_INTERVIEW, Command("back"))
@router.message(InterviewState.IN_INTERVIEW_LONG_ANSWER, Command("back"))
async def handle_back(message: Message, state: FSMContext) -> None:
    """Вернуться на один вопрос назад, чтобы изменить уже данный ответ.

    Бот покажет предыдущий вопрос вместе с текущим (сохранённым ранее)
    ответом. Новый текст перезапишет старый через accept_answer с
    allow_update=True — progress_count не двигается, потому что слот
    уже посчитан. После правки респондент возвращается на frontier
    (тот вопрос, где был до /back).
    """
    data = await state.get_data()
    session_id = data.get(DATA_SESSION_ID)
    campaign_id = data.get(DATA_CAMPAIGN_ID)
    current_question_id = data.get(DATA_CURRENT_QUESTION_ID)
    if session_id is None or campaign_id is None or current_question_id is None:
        await message.answer(messages.BACK_OUTSIDE_INTERVIEW)
        return

    async with open_session() as db:
        from apps.api.db.repositories.sessions import fetch_campaign_script_questions

        fetched = await fetch_campaign_script_questions(db, int(campaign_id))
        if fetched is None:
            await message.answer(messages.INTERNAL_ERROR)
            return
        campaign_obj, script = fetched

        # /back во время паузы — отказ: ничего не пишем, не меняем FSM.
        if campaign_obj.status == CampaignStatus.PAUSED:
            await message.answer(messages.CAMPAIGN_PAUSED_REJECT)
            return
        if campaign_obj.status == CampaignStatus.COMPLETED:
            await message.answer(messages.CAMPAIGN_COMPLETED_REJECT)
            await state.clear()
            return
        if campaign_obj.status != CampaignStatus.RUNNING:
            await message.answer(messages.CAMPAIGN_PAUSED_REJECT)
            return

        questions: list[Question] = list(script.questions)
        current_index = next(
            (i for i, q in enumerate(questions) if q.id == int(current_question_id)), None
        )
        if current_index is None:
            await message.answer(messages.INTERNAL_ERROR)
            return
        if current_index == 0:
            await message.answer(messages.ALREADY_AT_FIRST_QUESTION)
            return

        prev_index = current_index - 1
        prev_q = questions[prev_index]
        previous_answer_text = await get_existing_answer_text(
            db, session_id=int(session_id), question_id=prev_q.id
        )

    # Из LONG_ANSWER /back сбрасывает накопленные чанки и возвращает в IN_INTERVIEW.
    current_state = await state.get_state()
    if current_state == InterviewState.IN_INTERVIEW_LONG_ANSWER.state:
        await state.update_data({DATA_PENDING_CHUNKS: []})
        await state.set_state(InterviewState.IN_INTERVIEW)

    await state.update_data({DATA_CURRENT_QUESTION_ID: prev_q.id})
    if previous_answer_text is not None:
        await message.answer(messages.PREVIOUS_ANSWER_PREFIX.format(text=previous_answer_text))
    await message.answer(format_question(prev_q, prev_index, len(questions)))


# ---- /skip — пропуск необязательного вопроса --------------------------------
# Регистрируем ДО handle_answer: Command("skip") должен сматчиться раньше,
# чем F.text, иначе `/skip` уехал бы в handle_answer и был бы отвергнут как
# текст без кириллицы.


@router.message(InterviewState.IN_INTERVIEW, Command("skip"))
@router.message(InterviewState.IN_INTERVIEW_LONG_ANSWER, Command("skip"))
async def handle_skip(message: Message, state: FSMContext) -> None:
    """Пропустить текущий вопрос, если он не обязательный.

    Обязательные → отказ; необязательные → progress_count += 1, без
    сохранения Answer. В состоянии LONG_ANSWER чанки сбрасываются, FSM
    переключается обратно в IN_INTERVIEW.
    """
    data = await state.get_data()
    session_id = data.get(DATA_SESSION_ID)
    campaign_id = data.get(DATA_CAMPAIGN_ID)
    current_question_id = data.get(DATA_CURRENT_QUESTION_ID)
    if session_id is None or campaign_id is None or current_question_id is None:
        await message.answer(messages.SKIP_OUTSIDE_INTERVIEW)
        return

    async with open_session() as db:
        from apps.api.db.models import InterviewSession
        from apps.api.db.repositories.sessions import fetch_campaign_script_questions

        fetched = await fetch_campaign_script_questions(db, int(campaign_id))
        if fetched is None:
            await message.answer(messages.INTERNAL_ERROR)
            return
        campaign_obj, script = fetched

        # Те же status-гарды, что и для accept_answer.
        if campaign_obj.status == CampaignStatus.PAUSED:
            await message.answer(messages.CAMPAIGN_PAUSED_REJECT)
            return
        if campaign_obj.status == CampaignStatus.COMPLETED:
            await message.answer(messages.CAMPAIGN_COMPLETED_REJECT)
            await state.clear()
            return
        if campaign_obj.status != CampaignStatus.RUNNING:
            await message.answer(messages.CAMPAIGN_PAUSED_REJECT)
            return

        questions: list[Question] = list(script.questions)
        current_index = next(
            (i for i, q in enumerate(questions) if q.id == int(current_question_id)), None
        )
        if current_index is None:
            await message.answer(messages.INTERNAL_ERROR)
            return
        current = questions[current_index]

        if current.is_required:
            await message.answer(messages.QUESTION_REQUIRED_REJECT)
            return

        session_obj = await db.get(InterviewSession, int(session_id))
        progress_count = session_obj.progress_count if session_obj is not None else 0
        is_editing = current_index < progress_count

        try:
            result = await skip_question(
                db,
                session_id=int(session_id),
                current_question=current,
                questions=questions,
                allow_no_increment=is_editing,
            )
        except Exception as exc:
            logger.exception("skip_question failed: %s", exc)
            await message.answer(messages.INTERNAL_ERROR)
            return

        if result.is_last:
            await mark_completed(db, int(session_id))
            await maybe_notify_researcher_all_completed(db, campaign_id=int(campaign_id))
            previous_for_next = None
        elif result.next_question is not None:
            previous_for_next = await get_existing_answer_text(
                db, session_id=int(session_id), question_id=result.next_question.id
            )
        else:
            previous_for_next = None

    # Если пропускали из LONG_ANSWER — сбросить накопленные чанки и
    # вернуться в IN_INTERVIEW (на случай продолжения интервью).
    current_state = await state.get_state()
    if current_state == InterviewState.IN_INTERVIEW_LONG_ANSWER.state:
        await state.update_data({DATA_PENDING_CHUNKS: []})
        await state.set_state(InterviewState.IN_INTERVIEW)

    await _send_next_or_complete(
        message,
        state,
        result,
        questions,
        ack=messages.QUESTION_SKIPPED_ACCEPTED,
        previous_answer_text=previous_for_next,
    )


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
        from apps.api.db.models import InterviewSession
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
        current_index = next((i for i, q in enumerate(questions) if q.id == question_id), None)
        # progress_count — высокая отметка «уже посчитанных» слотов. Если
        # текущий индекс ниже неё, респондент вернулся через /back и сейчас
        # правит ранее данный ответ (или впервые отвечает на ранее
        # пропущенный вопрос).
        session_obj = await db.get(InterviewSession, session_id)
        progress_count = session_obj.progress_count if session_obj is not None else 0
        is_editing = current_index is not None and current_index < progress_count

        try:
            result = await accept_answer(
                db,
                session_id=session_id,
                question_id=question_id,
                text=text,
                questions=questions,
                allow_update=is_editing,
            )
        except Exception as exc:
            logger.exception("accept_answer failed: %s", exc)
            await message.answer(messages.INTERNAL_ERROR)
            return

        if result.is_last:
            await mark_completed(db, session_id)
            await maybe_notify_researcher_all_completed(db, campaign_id=campaign_id)
            previous_for_next = None
        elif result.next_question is not None:
            # При возврате на frontier после правки следующий вопрос может
            # уже иметь сохранённый ответ — покажем его респонденту.
            previous_for_next = await get_existing_answer_text(
                db, session_id=session_id, question_id=result.next_question.id
            )
        else:
            previous_for_next = None

    # Подтверждение (только после commit-а в accept_answer).
    ack = messages.ANSWER_UPDATED_SHORT if is_editing else messages.ANSWER_ACCEPTED_SHORT
    await _send_next_or_complete(
        message,
        state,
        result,
        questions,
        ack=ack,
        previous_answer_text=previous_for_next,
    )


async def _send_next_or_complete(
    message: Message,
    state: FSMContext,
    result: AnswerResult,
    questions: list[Question],
    *,
    ack: str,
    previous_answer_text: str | None = None,
) -> None:
    """После accept_answer/skip_question отправить следующий вопрос или
    финальное сообщение. `ack` — подтверждение действия (принято/пропущено).
    `previous_answer_text` — если следующий вопрос уже когда-то отвечался,
    показываем сохранённый ответ перед текстом вопроса."""
    if not result.is_last and result.next_question is not None:
        index = next((i for i, q in enumerate(questions) if q.id == result.next_question.id), 0)
        await state.update_data({DATA_CURRENT_QUESTION_ID: result.next_question.id})
        await message.answer(ack)
        if previous_answer_text is not None:
            await message.answer(messages.PREVIOUS_ANSWER_PREFIX.format(text=previous_answer_text))
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
