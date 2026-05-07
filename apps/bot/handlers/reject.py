"""Глобальный fallback на non-text сообщения вне FSM (FR-BOT-04).

Срабатывает, когда пользователь шлёт voice/photo/video/document/etc.
БЕЗ открытой сессии (state == None). Внутри активного интервью
аналогичная логика — в handlers/interview.py.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from apps.bot import messages

router = Router(name="bot.reject")


@router.message(~F.text)
async def reject_non_text_outside_interview(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is not None:
        # внутри интервью — пусть отрабатывает interview-роутер
        return
    await message.answer(messages.NON_TEXT_REJECTED)
