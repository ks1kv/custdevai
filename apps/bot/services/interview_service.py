"""Поток интервью: рендеринг вопроса, ACID-приём ответа (FR-BOT-02, 03, 07, 08; FR-DB-02; FR-API-08)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models import Answer, InterviewSession, Question
from apps.bot import messages

# Лимит длины одного сообщения Telegram. Совпадает с верхней границей
# CHECK-constraint answers_text_length (FR-BOT-08).
MAX_ANSWER_LENGTH = 4096


@dataclass(frozen=True)
class AnswerResult:
    """Результат accept_answer для handler-а."""

    inserted: bool  # True если был реальный INSERT, False если ON CONFLICT
    is_last: bool  # это был последний вопрос?
    next_question: Question | None  # вопрос, который надо отправить дальше


def format_question(question: Question, index: int, total: int) -> str:
    body = messages.QUESTION_TEMPLATE.format(idx=index + 1, total=total, text=question.text)
    if question.hint_text:
        body += messages.QUESTION_HINT_SUFFIX.format(hint=question.hint_text)
    return body


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


async def accept_answer(
    db: AsyncSession,
    *,
    session_id: int,
    question_id: int,
    text: str,
    questions: list[Question],
) -> AnswerResult:
    """ACID-транзакция INSERT answer + UPDATE sessions.progress_count (FR-DB-02).

    Идемпотентность по UNIQUE(session_id, question_id) (FR-API-08): повторный
    update от Telegram конфликтует и не порождает дубль; counter
    инкрементируется только при реальном INSERT.

    Подтверждение респонденту отправляется handler-ом ТОЛЬКО после успешного
    commit() этой функции. При rollback handler покажет INTERNAL_ERROR.

    Не открываем здесь явный `db.begin()` — в SQLAlchemy 2.x сессия уже
    находится в autobegin-состоянии после предыдущих `db.get(...)` из
    handler-а (например, fetch_campaign_script_questions). Все DML в этой
    функции исполняются внутри той же транзакции, и commit её закрывает —
    ACID-гарантия не страдает. Открытие явного `db.begin()` поверх
    autobegin кидает InvalidRequestError.
    """
    now = _utcnow()
    stmt = (
        pg_insert(Answer)
        .values(
            session_id=session_id,
            question_id=question_id,
            text=text,
            answered_at=now,
        )
        .on_conflict_do_nothing(index_elements=["session_id", "question_id"])
        .returning(Answer.id)
    )
    result = await db.execute(stmt)
    inserted_id = result.scalar_one_or_none()
    inserted = inserted_id is not None

    if inserted:
        await db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(
                progress_count=InterviewSession.progress_count + 1,
                last_activity_at=now,
            )
        )
    else:
        # Сообщение-дубль: counter не трогаем, но last_activity_at
        # обновляем, чтобы 48-часовое окно считалось от последнего
        # реального действия пользователя (FR-BOT-05).
        await db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(last_activity_at=now)
        )
    await db.commit()

    # После commit-а нужно решить: какой следующий вопрос отправлять.
    # Перечитываем session с новым progress_count.
    session = await db.get(InterviewSession, session_id)
    next_index = session.progress_count if session is not None else len(questions)
    is_last = next_index >= len(questions)
    next_question = None if is_last else questions[next_index]
    return AnswerResult(
        inserted=inserted,
        is_last=is_last,
        next_question=next_question,
    )
