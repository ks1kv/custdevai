"""Bot service-level integration: основной поток интервью (FR-BOT-01..07; FR-DB-02; FR-API-08).

Тестируется на уровне сервисов (begin_session, record_consent, accept_answer,
mark_*) — это покрывает критические инварианты ACID и идемпотентности
без обвязки aiogram-handler-ов.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio

from apps.api.db.models import (
    Answer,
    Campaign,
    CampaignStatus,
    Consent,
    InterviewSession,
    Question,
    Script,
    SessionStatus,
    User,
)
from apps.bot.messages import CURRENT_CONSENT_VERSION
from apps.bot.services.consent_service import record_consent
from apps.bot.services.interview_service import accept_answer
from apps.bot.services.session_service import (
    begin_session,
    mark_completed,
    mark_interrupted,
)


def _utcnaive(t: datetime | None = None) -> datetime:
    return (t or datetime.now(tz=timezone.utc)).replace(tzinfo=None)


@pytest_asyncio.fixture
async def seeded_running_campaign(db_session) -> dict[str, int]:
    """Кампания со сценарием из 3 вопросов, status=RUNNING, владелец-исследователь."""
    user = User(
        email="r@x.com",
        password_hash="$2b$12$" + "a" * 53,
    )
    db_session.add(user)
    await db_session.flush()

    script = Script(title="S", description=None, created_by_user_id=user.id)
    db_session.add(script)
    await db_session.flush()
    for i, text in enumerate(["Вопрос 1?", "Вопрос 2?", "Вопрос 3?"]):
        db_session.add(Question(script_id=script.id, order_index=i, text=text, is_required=True))
    await db_session.flush()

    campaign = Campaign(
        title="К1",
        script_id=script.id,
        created_by_user_id=user.id,
        status=CampaignStatus.RUNNING,
        pseudonym_salt=b"\x00" * 32,
        started_at=_utcnaive(),
    )
    db_session.add(campaign)
    await db_session.commit()
    return {"campaign_id": campaign.id, "script_id": script.id, "user_id": user.id}


@pytest.mark.asyncio
async def test_begin_session_creates_new(db_session, seeded_running_campaign) -> None:
    ctx = await begin_session(
        db_session,
        campaign_id=seeded_running_campaign["campaign_id"],
        telegram_user_id=12345,
    )
    assert ctx is not None
    assert ctx.is_new_session is True
    assert ctx.is_completed is False
    assert ctx.session.status == SessionStatus.ACTIVE
    assert len(ctx.session.telegram_id_hash) == 32
    assert len(ctx.questions) == 3


@pytest.mark.asyncio
async def test_begin_session_returns_none_for_non_running(db_session) -> None:
    user = User(email="r2@x.com", password_hash="$2b$12$" + "a" * 53)
    db_session.add(user)
    await db_session.flush()
    script = Script(title="S2", created_by_user_id=user.id)
    db_session.add(script)
    await db_session.flush()
    db_session.add(Question(script_id=script.id, order_index=0, text="?"))
    campaign = Campaign(
        title="K2",
        script_id=script.id,
        created_by_user_id=user.id,
        status=CampaignStatus.DRAFT,
        pseudonym_salt=b"\x00" * 32,
    )
    db_session.add(campaign)
    await db_session.commit()

    ctx = await begin_session(db_session, campaign_id=campaign.id, telegram_user_id=42)
    assert ctx is None  # FR-BOT-01: не запускаем интервью на DRAFT


@pytest.mark.asyncio
async def test_begin_session_resumes_active(db_session, seeded_running_campaign) -> None:
    cid = seeded_running_campaign["campaign_id"]
    ctx1 = await begin_session(db_session, campaign_id=cid, telegram_user_id=777)
    assert ctx1 is not None and ctx1.is_new_session is True

    ctx2 = await begin_session(db_session, campaign_id=cid, telegram_user_id=777)
    assert ctx2 is not None
    assert ctx2.is_new_session is False
    assert ctx2.session.id == ctx1.session.id  # та же сессия


@pytest.mark.asyncio
async def test_telegram_id_is_only_hashed(db_session, seeded_running_campaign) -> None:
    """FR-BOT-10: открытый telegram_id нигде не сохраняется."""
    cid = seeded_running_campaign["campaign_id"]
    tg_id = 9999999
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=tg_id)
    assert ctx is not None
    # Хеш не равен ни одному «человекочитаемому» представлению tg_id.
    assert ctx.session.telegram_id_hash != str(tg_id).encode()
    assert tg_id.to_bytes(8, "big") not in ctx.session.telegram_id_hash


@pytest.mark.asyncio
async def test_record_consent_is_idempotent(db_session, seeded_running_campaign) -> None:
    """FR-BOT-01: двойное нажатие кнопки → ровно одна запись Consent."""
    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=11)
    assert ctx is not None

    is_new1 = await record_consent(
        db_session, session_id=ctx.session.id, consent_version=CURRENT_CONSENT_VERSION
    )
    is_new2 = await record_consent(
        db_session, session_id=ctx.session.id, consent_version=CURRENT_CONSENT_VERSION
    )
    assert is_new1 is True
    assert is_new2 is False

    from sqlalchemy import select

    rows = (
        (await db_session.execute(select(Consent).where(Consent.session_id == ctx.session.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_accept_answer_is_acid_and_increments_counter(
    db_session, seeded_running_campaign
) -> None:
    """FR-DB-02 ACID: INSERT answer + UPDATE progress_count в одной транзакции.

    Проверяем, что после accept_answer counter инкрементировался ровно на 1
    и Answer присутствует.
    """
    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=22)
    assert ctx is not None

    result = await accept_answer(
        db_session,
        session_id=ctx.session.id,
        question_id=ctx.questions[0].id,
        text="мой ответ",
        questions=ctx.questions,
    )
    assert result.inserted is True
    assert result.is_last is False

    # Проверяем БД
    from sqlalchemy import select

    answers = (
        (await db_session.execute(select(Answer).where(Answer.session_id == ctx.session.id)))
        .scalars()
        .all()
    )
    assert len(answers) == 1
    assert answers[0].text == "мой ответ"

    fresh_session = await db_session.get(InterviewSession, ctx.session.id)
    assert fresh_session is not None
    assert fresh_session.progress_count == 1


@pytest.mark.asyncio
async def test_accept_answer_idempotent_on_duplicate(db_session, seeded_running_campaign) -> None:
    """FR-API-08: повторный update от Telegram не порождает дубль."""
    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=33)
    assert ctx is not None

    r1 = await accept_answer(
        db_session,
        session_id=ctx.session.id,
        question_id=ctx.questions[0].id,
        text="первый",
        questions=ctx.questions,
    )
    r2 = await accept_answer(
        db_session,
        session_id=ctx.session.id,
        question_id=ctx.questions[0].id,
        text="второй",  # текст другой — но (session, question) тот же
        questions=ctx.questions,
    )
    assert r1.inserted is True
    assert r2.inserted is False  # ON CONFLICT DO NOTHING

    from sqlalchemy import select

    answers = (
        (await db_session.execute(select(Answer).where(Answer.session_id == ctx.session.id)))
        .scalars()
        .all()
    )
    assert len(answers) == 1  # дубля нет
    assert answers[0].text == "первый"


@pytest.mark.asyncio
async def test_skip_question_advances_counter_without_answer(
    db_session, seeded_running_campaign
) -> None:
    """Пропуск необязательного вопроса: progress_count += 1, Answer не создаётся."""
    from sqlalchemy import select

    from apps.api.db.models import Question
    from apps.bot.services.interview_service import skip_question

    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=55)
    assert ctx is not None

    # Сделаем первый вопрос необязательным для теста.
    first_q = ctx.questions[0]
    first_q.is_required = False
    await db_session.commit()
    # Перечитываем, чтобы получить чистое состояние.
    fresh_first = await db_session.get(Question, first_q.id)
    assert fresh_first is not None and fresh_first.is_required is False

    result = await skip_question(
        db_session,
        session_id=ctx.session.id,
        current_question=fresh_first,
        questions=ctx.questions,
    )
    assert result.inserted is False
    assert result.is_last is False
    assert result.next_question is not None
    assert result.next_question.id == ctx.questions[1].id

    # В БД Answer-а нет.
    answers = (
        (await db_session.execute(select(Answer).where(Answer.session_id == ctx.session.id)))
        .scalars()
        .all()
    )
    assert answers == []

    # progress_count увеличился на 1.
    refreshed = await db_session.get(InterviewSession, ctx.session.id)
    assert refreshed is not None and refreshed.progress_count == 1


@pytest.mark.asyncio
async def test_skip_question_refuses_required(db_session, seeded_running_campaign) -> None:
    """ValueError при попытке пропустить обязательный вопрос."""
    from apps.bot.services.interview_service import skip_question

    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=56)
    assert ctx is not None
    # Дефолтные вопросы из conftest идут required=True; проверяем.
    assert ctx.questions[0].is_required is True

    with pytest.raises(ValueError, match="required"):
        await skip_question(
            db_session,
            session_id=ctx.session.id,
            current_question=ctx.questions[0],
            questions=ctx.questions,
        )

    # progress_count не сдвинулся.
    refreshed = await db_session.get(InterviewSession, ctx.session.id)
    assert refreshed is not None and refreshed.progress_count == 0


@pytest.mark.asyncio
async def test_accept_answer_allow_update_overwrites_existing(
    db_session, seeded_running_campaign
) -> None:
    """allow_update=True (после /back) перезаписывает текст ответа и НЕ
    инкрементирует progress_count повторно."""
    from sqlalchemy import select

    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=77)
    assert ctx is not None
    qid = ctx.questions[0].id

    # Первый раз — обычный forward
    r1 = await accept_answer(
        db_session,
        session_id=ctx.session.id,
        question_id=qid,
        text="первый вариант",
        questions=ctx.questions,
    )
    assert r1.inserted is True

    sess = await db_session.get(InterviewSession, ctx.session.id)
    assert sess is not None and sess.progress_count == 1

    # /back возвращает на этот же вопрос, респондент переписывает ответ
    r2 = await accept_answer(
        db_session,
        session_id=ctx.session.id,
        question_id=qid,
        text="ИСПРАВЛЕННЫЙ ответ",
        questions=ctx.questions,
        allow_update=True,
    )
    assert r2.inserted is False  # это правка, не новый слот

    # progress_count не сдвинулся
    sess = await db_session.get(InterviewSession, ctx.session.id)
    assert sess is not None and sess.progress_count == 1

    # В БД именно новый текст
    rows = (
        (await db_session.execute(select(Answer).where(Answer.question_id == qid))).scalars().all()
    )
    assert len(rows) == 1
    assert rows[0].text == "ИСПРАВЛЕННЫЙ ответ"


@pytest.mark.asyncio
async def test_accept_answer_allow_update_inserts_when_no_prior(
    db_session, seeded_running_campaign
) -> None:
    """allow_update=True над ранее пропущенным (но не отвеченным) вопросом
    создаёт новую строку Answer."""
    from sqlalchemy import select

    from apps.api.db.models import Question
    from apps.bot.services.interview_service import skip_question

    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=78)
    assert ctx is not None

    # Делаем первый вопрос необязательным и пропускаем его.
    first_q = ctx.questions[0]
    first_q.is_required = False
    await db_session.commit()
    fresh = await db_session.get(Question, first_q.id)
    assert fresh is not None
    await skip_question(
        db_session,
        session_id=ctx.session.id,
        current_question=fresh,
        questions=ctx.questions,
    )
    # progress_count == 1, Answer на Q1 не было.
    sess = await db_session.get(InterviewSession, ctx.session.id)
    assert sess is not None and sess.progress_count == 1

    # /back → правка Q1: теперь хотим записать ответ.
    r = await accept_answer(
        db_session,
        session_id=ctx.session.id,
        question_id=first_q.id,
        text="теперь хочу ответить",
        questions=ctx.questions,
        allow_update=True,
    )
    # В edit-режиме inserted=False по семантике слотов (слот уже считался).
    assert r.inserted is False

    sess = await db_session.get(InterviewSession, ctx.session.id)
    assert sess is not None and sess.progress_count == 1  # без изменений

    rows = (
        (await db_session.execute(select(Answer).where(Answer.session_id == ctx.session.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].text == "теперь хочу ответить"


@pytest.mark.asyncio
async def test_get_existing_answer_text_returns_saved(db_session, seeded_running_campaign) -> None:
    """get_existing_answer_text возвращает сохранённый текст / None."""
    from apps.bot.services.interview_service import get_existing_answer_text

    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=79)
    assert ctx is not None
    qid = ctx.questions[0].id

    # До ответа — None.
    assert (
        await get_existing_answer_text(db_session, session_id=ctx.session.id, question_id=qid)
        is None
    )

    await accept_answer(
        db_session,
        session_id=ctx.session.id,
        question_id=qid,
        text="мой ответ",
        questions=ctx.questions,
    )
    got = await get_existing_answer_text(db_session, session_id=ctx.session.id, question_id=qid)
    assert got == "мой ответ"


@pytest.mark.asyncio
async def test_skip_question_with_allow_no_increment_does_not_advance(
    db_session, seeded_running_campaign
) -> None:
    """В режиме правки /skip не сдвигает progress_count."""
    from apps.api.db.models import Question
    from apps.bot.services.interview_service import skip_question

    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=80)
    assert ctx is not None
    # Сделать первый вопрос необязательным.
    first_q = ctx.questions[0]
    first_q.is_required = False
    await db_session.commit()
    fresh = await db_session.get(Question, first_q.id)
    assert fresh is not None

    # forward-skip → progress_count = 1
    await skip_question(
        db_session,
        session_id=ctx.session.id,
        current_question=fresh,
        questions=ctx.questions,
    )
    sess = await db_session.get(InterviewSession, ctx.session.id)
    assert sess is not None and sess.progress_count == 1

    # Имитируем «/back + /skip»: allow_no_increment=True не должно
    # сдвинуть progress_count.
    await skip_question(
        db_session,
        session_id=ctx.session.id,
        current_question=fresh,
        questions=ctx.questions,
        allow_no_increment=True,
    )
    sess = await db_session.get(InterviewSession, ctx.session.id)
    assert sess is not None and sess.progress_count == 1


@pytest.mark.asyncio
async def test_accept_answer_works_when_session_already_in_transaction(
    db_session, seeded_running_campaign
) -> None:
    """Регрессия: handler-flow в боте делает fetch_campaign_script_questions
    (db.get → autobegin) и сразу после — accept_answer. Раньше внутри
    accept_answer был лишний `async with db.begin():`, который падал
    с InvalidRequestError на active-транзакции и отдавал пользователю
    «Не удалось сохранить ответ.»
    """
    from apps.api.db.repositories.sessions import fetch_campaign_script_questions

    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=99)
    assert ctx is not None
    sid = ctx.session.id
    qid = ctx.questions[0].id

    # Имитируем handler: первый db.get запускает autobegin.
    fetched = await fetch_campaign_script_questions(db_session, cid)
    assert fetched is not None
    assert db_session.in_transaction()

    # accept_answer не должен бросать InvalidRequestError, несмотря
    # на уже активную транзакцию сессии.
    result = await accept_answer(
        db_session,
        session_id=sid,
        question_id=qid,
        text="ответ из handler-flow",
        questions=ctx.questions,
    )
    assert result.inserted is True

    # progress_count не вырос на дубле — увеличился только один раз
    fresh = await db_session.get(InterviewSession, ctx.session.id)
    assert fresh is not None and fresh.progress_count == 1


@pytest.mark.asyncio
async def test_full_flow_completes(db_session, seeded_running_campaign) -> None:
    """FR-BOT-07: после ответа на последний вопрос — статус COMPLETED."""
    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=44)
    assert ctx is not None

    for q in ctx.questions:
        await accept_answer(
            db_session,
            session_id=ctx.session.id,
            question_id=q.id,
            text=f"ответ на {q.text}",
            questions=ctx.questions,
        )
    # Последний accept_answer вернёт is_last=True; handler сам вызывает
    # mark_completed. Сделаем это в тесте явно.
    await mark_completed(db_session, ctx.session.id)

    fresh = await db_session.get(InterviewSession, ctx.session.id)
    assert fresh is not None
    assert fresh.status == SessionStatus.COMPLETED
    assert fresh.completed_at is not None
    assert fresh.progress_count == 3


@pytest.mark.asyncio
async def test_stop_preserves_answers(db_session, seeded_running_campaign) -> None:
    """FR-BOT-06: /stop сохраняет ответы и помечает сессию INTERRUPTED."""
    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=55)
    assert ctx is not None

    await accept_answer(
        db_session,
        session_id=ctx.session.id,
        question_id=ctx.questions[0].id,
        text="успели ответить",
        questions=ctx.questions,
    )
    await mark_interrupted(db_session, ctx.session.id)

    fresh = await db_session.get(InterviewSession, ctx.session.id)
    assert fresh is not None and fresh.status == SessionStatus.INTERRUPTED

    from sqlalchemy import select

    answers = (
        (await db_session.execute(select(Answer).where(Answer.session_id == ctx.session.id)))
        .scalars()
        .all()
    )
    assert len(answers) == 1
    assert answers[0].text == "успели ответить"


@pytest.mark.asyncio
async def test_completed_session_returns_already_completed(
    db_session, seeded_running_campaign
) -> None:
    cid = seeded_running_campaign["campaign_id"]
    ctx = await begin_session(db_session, campaign_id=cid, telegram_user_id=66)
    assert ctx is not None
    await mark_completed(db_session, ctx.session.id)

    ctx2 = await begin_session(db_session, campaign_id=cid, telegram_user_id=66)
    assert ctx2 is not None
    assert ctx2.is_completed is True
