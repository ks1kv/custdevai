"""Интеграционный тест FR-DB-07 — безвозвратное удаление данных субъекта.

Проверяет полный сценарий 152-ФЗ-удаления:
- session + answers + sentiment_results + consents удаляются;
- audit_log получает запись data_deletion_requested с counts;
- сессии других субъектов не задеты;
- эндпоинт защищён ролью Admin.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from apps.api.db.models import (
    Answer,
    AuditAction,
    AuditLog,
    Campaign,
    CampaignStatus,
    Consent,
    InterviewSession,
    Question,
    Script,
    SentimentLabel,
    SentimentResult,
    SessionStatus,
)
from apps.api.services.data_deletion import DataDeletionService


async def _login(client, email: str, password: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


async def _seed_subject(db_session, admin_id: int, telegram_hash: bytes) -> dict:
    """Создать кампанию + сценарий + сессию с ответами + sentiment для субъекта."""
    script = Script(title="S", created_by_user_id=admin_id)
    db_session.add(script)
    await db_session.flush()
    q = Question(script_id=script.id, text="Что вас беспокоит?", order_index=0, is_required=True)
    db_session.add(q)
    await db_session.flush()
    campaign = Campaign(
        title="C",
        script_id=script.id,
        created_by_user_id=admin_id,
        status=CampaignStatus.RUNNING,
        pseudonym_salt=b"0" * 32,
    )
    db_session.add(campaign)
    await db_session.flush()

    session = InterviewSession(
        campaign_id=campaign.id,
        telegram_id_hash=telegram_hash,
        status=SessionStatus.COMPLETED,
        progress_count=1,
        last_activity_at=datetime.now(tz=timezone.utc).replace(tzinfo=None),
    )
    db_session.add(session)
    await db_session.flush()

    db_session.add(
        Consent(
            session_id=session.id,
            consent_version="v1",
            ip_address_hash=b"\x11" * 32,
        )
    )
    answer = Answer(
        session_id=session.id,
        question_id=q.id,
        text="Поиск тормозит",
        answered_at=datetime.now(tz=timezone.utc).replace(tzinfo=None),
    )
    db_session.add(answer)
    await db_session.flush()
    db_session.add(
        SentimentResult(
            answer_id=answer.id,
            label=SentimentLabel.NEGATIVE,
            confidence=0.91,
            analyzed_at=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        )
    )
    await db_session.commit()
    return {
        "campaign_id": campaign.id,
        "script_id": script.id,
        "question_id": q.id,
        "session_id": session.id,
        "answer_id": answer.id,
    }


@pytest.mark.asyncio
async def test_data_deletion_service_removes_all_subject_records(db_session, seeded_admin):
    hash_target = b"\xaa" * 32
    hash_other = b"\xbb" * 32
    target = await _seed_subject(db_session, seeded_admin["id"], hash_target)
    other = await _seed_subject(db_session, seeded_admin["id"], hash_other)

    service = DataDeletionService(db_session)
    receipt = await service.delete_by_telegram_hash(
        hash_target,
        actor_user_id=seeded_admin["id"],
        ip_address="127.0.0.1",
    )

    # Acт удаления корректен.
    assert receipt.telegram_id_hash_hex == hash_target.hex()
    assert receipt.affected["interview_sessions"] == 1
    assert receipt.affected["answers"] == 1
    assert receipt.affected["sentiment_results"] == 1
    assert receipt.affected["consents"] == 1
    assert receipt.audit_id is not None

    # Сессия и связанные данные субъекта удалены полностью.
    assert (
        await db_session.execute(
            select(InterviewSession).where(InterviewSession.telegram_id_hash == hash_target)
        )
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(Answer).where(Answer.session_id == target["session_id"]))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(
            select(SentimentResult).where(SentimentResult.answer_id == target["answer_id"])
        )
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(Consent).where(Consent.session_id == target["session_id"]))
    ).scalar_one_or_none() is None

    # Чужой субъект не задет.
    other_session = (
        await db_session.execute(
            select(InterviewSession).where(InterviewSession.telegram_id_hash == hash_other)
        )
    ).scalar_one()
    assert other_session.id == other["session_id"]

    # Audit-log получил запись.
    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == AuditAction.DATA_DELETION_REQUESTED)
        )
    ).scalar_one()
    assert audit.user_id == seeded_admin["id"]
    assert "legal_basis" in audit.details
    assert audit.details["affected"]["sentiment_results"] == 1


@pytest.mark.asyncio
async def test_data_deletion_raises_when_no_subject(db_session):
    service = DataDeletionService(db_session)
    from apps.api.errors import NotFound

    with pytest.raises(NotFound):
        await service.delete_by_telegram_hash(b"\xff" * 32, actor_user_id=None, ip_address=None)


@pytest.mark.asyncio
async def test_admin_endpoint_requires_admin_role(client, seeded_admin, db_session):
    # Без логина — 401.
    r = await client.post(
        "/api/v1/admin/data-deletion-requests",
        json={"telegram_id_hash": "ab" * 32},
    )
    assert r.status_code == 401

    # Admin может вызвать; но субъекта нет → 404 RFC 7807.
    token = await _login(client, seeded_admin["email"], seeded_admin["password"])
    r = await client.post(
        "/api/v1/admin/data-deletion-requests",
        json={"telegram_id_hash": "ab" * 32},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_admin_endpoint_validates_hex_length(client, seeded_admin):
    token = await _login(client, seeded_admin["email"], seeded_admin["password"])
    r = await client.post(
        "/api/v1/admin/data-deletion-requests",
        json={"telegram_id_hash": "ab"},  # not 64 hex chars
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400 or r.status_code == 422
