"""Inline-клавиатуры бота."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CONSENT_CALLBACK = "consent:yes"
LONG_ANSWER_DONE_CALLBACK = "long:done"


def consent_keyboard() -> InlineKeyboardMarkup:
    """Кнопка подтверждения согласия (FR-BOT-01)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Согласен на участие", callback_data=CONSENT_CALLBACK)]
        ]
    )


def long_answer_done_keyboard() -> InlineKeyboardMarkup:
    """Кнопка «Готово» для склейки длинного ответа (FR-BOT-08)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data=LONG_ANSWER_DONE_CALLBACK)]
        ]
    )
