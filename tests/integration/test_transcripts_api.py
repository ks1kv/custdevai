"""Тесты transcripts endpoint (FR-WEB-05)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.api.db.models import (
    Answer,
    Campaign,
    CampaignStatus,
    InterviewSession,
    Question,
    Script,
    SentimentLabel,
    SentimentResult,
    SessionStatus,
)


async def _login(client, email: str, password: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


@pytest.fixture()
async def seeded_campaign(db_session, seeded_admin):
    """Кампания с 2 сессиями и 3 ответами + sentiment-результаты."""
    script = Script(title="S", created_by_user_id=seeded_admin["id"])
    db_session.add(script)
    await db_session.flush()
    q1 = Question(script_id=script.id, text="Q1?", order_index=0, is_required=True)
    q2 = Question(script_id=script.id, text="Q2?", order_index=1, is_required=True)
    db_session.add_all([q1, q2])
    await db_session.flush()

    campaign = Campaign(
        title="C",
        script_id=script.id,
        created_by_user_id=seeded_admin["id"],
        status=CampaignStatus.RUNNING,
        pseudonym_salt=b"0" * 32,
    )
    db_session.add(campaign)
    await db_session.flush()

    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    s1 = InterviewSession(
        campaign_id=campaign.id,
        telegram_id_hash=b"\x01" * 32,
        status=SessionStatus.COMPLETED,
        progress_count=2,
        last_activity_at=now,
    )
    s2 = InterviewSession(
        campaign_id=campaign.id,
        telegram_id_hash=b"\x02" * 32,
        status=SessionStatus.COMPLETED,
        progress_count=1,
        last_activity_at=now,
    )
    db_session.add_all([s1, s2])
    await db_session.flush()

    a1 = Answer(session_id=s1.id, question_id=q1.id, text="Поиск работает плохо", answered_at=now)
    a2 = Answer(session_id=s1.id, question_id=q2.id, text="Интерфейс перегружен", answered_at=now)
    a3 = Answer(session_id=s2.id, question_id=q1.id, text="Всё устраивает", answered_at=now)
    db_session.add_all([a1, a2, a3])
    await db_session.flush()

    db_session.add_all(
        [
            SentimentResult(
                answer_id=a1.id, label=SentimentLabel.NEGATIVE, confidence=0.9, analyzed_at=now
            ),
            SentimentResult(
                answer_id=a3.id, label=SentimentLabel.POSITIVE, confidence=0.8, analyzed_at=now
            ),
        ]
    )
    await db_session.commit()
    return {"campaign_id": campaign.id, "s1": s1.id, "s2": s2.id}


@pytest.mark.asyncio
async def test_list_transcripts_returns_all_sessions(client, seeded_admin, seeded_campaign):
    token = await _login(client, seeded_admin["email"], seeded_admin["password"])
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get(
        f"/api/v1/campaigns/{seeded_campaign['campaign_id']}/transcripts",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    s1_dto = next(it for it in body["items"] if it["session_id"] == seeded_campaign["s1"])
    assert s1_dto["pseudonym"].startswith("R-")
    # Ответы упорядочены по order_index вопроса.
    assert [a["question_order"] for a in s1_dto["answers"]] == [0, 1]
    # Sentiment-метка пробрасывается.
    assert s1_dto["answers"][0]["sentiment_label"] == "negative"


@pytest.mark.asyncio
async def test_list_transcripts_search_by_text(client, seeded_admin, seeded_campaign):
    token = await _login(client, seeded_admin["email"], seeded_admin["password"])
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get(
        f"/api/v1/campaigns/{seeded_campaign['campaign_id']}/transcripts?q=поиск",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    # Только s1 содержит «поиск».
    assert body["total"] == 1
    assert body["items"][0]["session_id"] == seeded_campaign["s1"]


@pytest.mark.asyncio
async def test_list_transcripts_filter_by_sentiment(client, seeded_admin, seeded_campaign):
    token = await _login(client, seeded_admin["email"], seeded_admin["password"])
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get(
        f"/api/v1/campaigns/{seeded_campaign['campaign_id']}/transcripts?sentiment=positive",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    # Только s2 имеет positive-ответ.
    assert body["total"] == 1
    assert body["items"][0]["session_id"] == seeded_campaign["s2"]


@pytest.mark.asyncio
async def test_list_transcripts_unauthorized(client, seeded_campaign):
    r = await client.get(f"/api/v1/campaigns/{seeded_campaign['campaign_id']}/transcripts")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_transcripts_not_found_for_other_campaign(client, seeded_admin):
    token = await _login(client, seeded_admin["email"], seeded_admin["password"])
    r = await client.get(
        "/api/v1/campaigns/99999/transcripts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
