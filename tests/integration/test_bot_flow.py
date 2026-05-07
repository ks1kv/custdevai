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
