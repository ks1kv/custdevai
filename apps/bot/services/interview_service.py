"""Поток интервью: рендеринг вопроса, ACID-приём ответа (FR-BOT-02, 03, 07, 08; FR-DB-02; FR-API-08)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
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
    if not question.is_required:
        body += messages.QUESTION_OPTIONAL_SUFFIX
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
    allow_update: bool = False,
) -> AnswerResult:
    """ACID-транзакция запись ответа + UPDATE sessions.progress_count (FR-DB-02).

    Два режима:

    `allow_update=False` (по умолчанию, forward-flow). Идемпотентность по
    UNIQUE(session_id, question_id) (FR-API-08): повторный update от
    Telegram конфликтует и не порождает дубль; progress_count
    инкрементируется только при реальном INSERT-е.

    `allow_update=True` (режим правки после /back). UPSERT: последний
    отправленный текст становится текущим. progress_count НЕ трогаем —
    это правка уже посчитанного слота. Handler должен выставлять
    allow_update=True только при current_index < progress_count.

    Подтверждение респонденту отправляется handler-ом ТОЛЬКО после
    успешного commit() этой функции. При rollback handler покажет
    INTERNAL_ERROR.

    Не открываем здесь явный `db.begin()` — в SQLAlchemy 2.x сессия уже
    находится в autobegin-состоянии после предыдущих `db.get(...)` из
    handler-а (например, fetch_campaign_script_questions). Все DML в этой
    функции исполняются внутри той же транзакции, и commit её закрывает —
    ACID-гарантия не страдает. Открытие явного `db.begin()` поверх
    autobegin кидает InvalidRequestError.
    """
    now = _utcnow()

    if allow_update:
        # UPSERT: текст всегда становится последним отправленным. Используем
        # ON CONFLICT DO UPDATE, чтобы не делать отдельный SELECT и быть
        # устойчивыми к гонкам с параллельным Telegram-retry.
        upsert_stmt = (
            pg_insert(Answer)
            .values(
                session_id=session_id,
                question_id=question_id,
                text=text,
                answered_at=now,
            )
            .on_conflict_do_update(
                index_elements=["session_id", "question_id"],
                set_={"text": text, "answered_at": now},
            )
        )
        await db.execute(upsert_stmt)
        await db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(last_activity_at=now)
        )
        inserted = False  # в режиме правки слот уже был посчитан ранее
    else:
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
    # Перечитываем session с новым progress_count (или прежним в режиме
    # правки — тогда вернёмся на frontier, на тот вопрос, где были до /back).
    session = await db.get(InterviewSession, session_id)
    next_index = session.progress_count if session is not None else len(questions)
    is_last = next_index >= len(questions)
    next_question = None if is_last else questions[next_index]
    return AnswerResult(
        inserted=inserted,
        is_last=is_last,
        next_question=next_question,
    )


async def get_existing_answer_text(
    db: AsyncSession, *, session_id: int, question_id: int
) -> str | None:
    """Вернуть текст ранее сохранённого ответа на этот вопрос, если есть.

    Нужен handler-у, чтобы при /back и при показе уже отвеченных вопросов
    префиксить сообщение «Ваш предыдущий ответ: …».
    """
    return await db.scalar(
        select(Answer.text).where(
            Answer.session_id == session_id, Answer.question_id == question_id
        )
    )


async def skip_question(
    db: AsyncSession,
    *,
    session_id: int,
    current_question: Question,
    questions: list[Question],
    allow_no_increment: bool = False,
) -> AnswerResult:
    """Пропустить необязательный вопрос.

    `allow_no_increment=False` (forward-flow): инкрементируем progress_count,
    Answer не пишем — слот считается завершённым «пропуском».

    `allow_no_increment=True` (правка после /back): respondent на ранее
    пройденном вопросе ввёл /skip; данные не трогаем (его прошлый ответ
    или пропуск остаются), progress_count не сдвигается, только
    last_activity_at. Возвращаемся на frontier.

    Поднимает ValueError, если current_question.is_required — handler
    обязан проверить is_required ДО вызова и показать пользователю
    QUESTION_REQUIRED_REJECT. ValueError тут — защита от пути в обход.
    """
    if current_question.is_required:
        raise ValueError("Cannot skip a required question")
    now = _utcnow()
    if allow_no_increment:
        await db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(last_activity_at=now)
        )
    else:
        await db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(
                progress_count=InterviewSession.progress_count + 1,
                last_activity_at=now,
            )
        )
    await db.commit()

    session = await db.get(InterviewSession, session_id)
    next_index = session.progress_count if session is not None else len(questions)
    is_last = next_index >= len(questions)
    next_question = None if is_last else questions[next_index]
    return AnswerResult(
        inserted=False,
        is_last=is_last,
        next_question=next_question,
    )
