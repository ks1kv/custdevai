"""Поток интервью: рендеринг вопроса, ACID-приём ответа (FR-BOT-02, 03, 07, 08; FR-DB-02)."""

from __future__ import annotations

from apps.api.db.models import Question
from apps.bot import messages


def format_question(question: Question, index: int, total: int) -> str:
    """Подсказка склеивается через QUESTION_HINT_SUFFIX (FR-BOT-02)."""
    body = messages.QUESTION_TEMPLATE.format(
        idx=index + 1, total=total, text=question.text
    )
    if question.hint_text:
        body += messages.QUESTION_HINT_SUFFIX.format(hint=question.hint_text)
    return body
