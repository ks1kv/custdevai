"""Тест sessions sweeper (FR-BOT-05).

После 48 часов неактивности sweeper переводит active-сессии в interrupted.
В тесте используем custom inactive_hours=1 для скорости.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from apps.api.db.models import (
    Campaign,
    CampaignStatus,
    InterviewSession,
    Script,
    SessionStatus,
)
from apps.worker.tasks.sessions import sweep_inactive


@pytest.mark.asyncio
async def test_sweeper_marks_inactive_as_interrupted(db_session, seeded_admin):
    # Setup: сценарий + кампания.
    script = Script(title="S", created_by_user_id=seeded_admin["id"])
    db_session.add(script)
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
    stale = InterviewSession(
        campaign_id=campaign.id,
        telegram_id_hash=b"a" * 32,
        status=SessionStatus.ACTIVE,
        last_activity_at=now - timedelta(hours=49),
        progress_count=0,
    )
    fresh = InterviewSession(
        campaign_id=campaign.id,
        telegram_id_hash=b"b" * 32,
        status=SessionStatus.ACTIVE,
        last_activity_at=now - timedelta(minutes=10),
        progress_count=0,
    )
    completed_stale = InterviewSession(
        campaign_id=campaign.id,
        telegram_id_hash=b"c" * 32,
        status=SessionStatus.COMPLETED,
        last_activity_at=now - timedelta(hours=49),
        progress_count=5,
    )
    db_session.add_all([stale, fresh, completed_stale])
    await db_session.commit()

    # Act
    result = await sweep_inactive(db_session, inactive_hours=48)

    # Assert
    assert result["swept"] == 1

    fresh_after = (
        await db_session.execute(select(InterviewSession).where(InterviewSession.id == fresh.id))
    ).scalar_one()
    assert fresh_after.status == SessionStatus.ACTIVE

    stale_after = (
        await db_session.execute(select(InterviewSession).where(InterviewSession.id == stale.id))
    ).scalar_one()
    assert stale_after.status == SessionStatus.INTERRUPTED

    completed_after = (
        await db_session.execute(
            select(InterviewSession).where(InterviewSession.id == completed_stale.id)
        )
    ).scalar_one()
    assert completed_after.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_sweeper_returns_zero_when_no_stale(db_session, seeded_admin):
    script = Script(title="S2", created_by_user_id=seeded_admin["id"])
    db_session.add(script)
    await db_session.flush()
    campaign = Campaign(
        title="C2",
        script_id=script.id,
        created_by_user_id=seeded_admin["id"],
        status=CampaignStatus.RUNNING,
        pseudonym_salt=b"0" * 32,
    )
    db_session.add(campaign)
    await db_session.commit()

    result = await sweep_inactive(db_session, inactive_hours=48)
    assert result["swept"] == 0
