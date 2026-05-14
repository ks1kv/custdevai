"""Общие хелперы для load-сценариев (синтетический seed).

Используется в scenario_2_ml_analyze.py и scenario_3_report_500.py.
Идея: создать одну кампанию + N сессий + по 5 ответов на каждую через
прямой insert (минуя бота и HTTP-эндпоинты), затем вызвать
ReportService / analyze_campaign в eager-режиме и замерить wall-time.

Это не имитирует пользовательский путь, а изолированно нагружает
CPU-bound операции — что и нужно для NFR-PRF-04/05.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.config import get_settings
from apps.api.db.models import (
    Answer,
    Campaign,
    CampaignAnalysisStatus,
    CampaignStatus,
    InterviewSession,
    Question,
    Script,
    SessionStatus,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)

# Тексты ответов — реалистичные русскоязычные фразы, чтобы ML-анализ
# не падал на лингвистическом фильтре (FR-SENT-06).
_SAMPLE_ANSWERS = [
    "Поиск работает медленно, не могу найти нужный товар.",
    "Очень удобный интерфейс, всё интуитивно понятно.",
    "Цены устраивают, но доставка дорогая.",
    "Категории товаров перегружены, тяжело ориентироваться.",
    "Качество поддержки приятно удивило.",
    "Хочу видеть больше отзывов от других покупателей.",
    "Приложение часто зависает на этапе оплаты.",
    "Часто пользуюсь акциями, экономлю заметно.",
    "Не понимаю, как оформить возврат через кабинет.",
    "Все нравится, продолжу пользоваться.",
]


async def _get_or_create_test_user(db: AsyncSession) -> int:
    """Создать или вернуть admin-пользователя для load-test seed."""
    existing = (
        await db.execute(select(User).where(User.email == "loadtest@custdevai.local"))
    ).scalar_one_or_none()
    if existing:
        return existing.id
    user = User(
        email="loadtest@custdevai.local",
        full_name="Load Test Owner",
        password_hash="$2b$12$loadtestplaceholder0000000000000000000000000",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    db.add(UserRole(user_id=user.id, role_id=1))  # admin role seeded в миграции 0001
    await db.commit()
    return user.id


async def seed_campaign_with_sessions(
    *,
    session_count: int,
    questions_per_script: int = 5,
    db: AsyncSession,
    rng_seed: int = 42,
) -> dict:
    """Создать campaign + script + sessions + answers."""
    rng = random.Random(rng_seed)
    owner_id = await _get_or_create_test_user(db)

    script = Script(title=f"Load-test {session_count} sessions", created_by_user_id=owner_id)
    db.add(script)
    await db.flush()

    questions: list[Question] = []
    for i in range(questions_per_script):
        q = Question(
            script_id=script.id,
            text=f"Тестовый вопрос {i + 1}?",
            order_index=i,
            is_required=True,
        )
        questions.append(q)
        db.add(q)
    await db.flush()

    campaign = Campaign(
        title=f"Load test {session_count}",
        script_id=script.id,
        created_by_user_id=owner_id,
        status=CampaignStatus.COMPLETED,
        pseudonym_salt=os.urandom(32),
        analysis_status=CampaignAnalysisStatus.COMPLETED,
        target_topic_count=10,
    )
    db.add(campaign)
    await db.flush()

    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    for i in range(session_count):
        session = InterviewSession(
            campaign_id=campaign.id,
            telegram_id_hash=rng.randbytes(32),
            status=SessionStatus.COMPLETED,
            progress_count=questions_per_script,
            started_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=1),
            last_activity_at=now - timedelta(hours=1),
        )
        db.add(session)
        await db.flush()
        for q in questions:
            db.add(
                Answer(
                    session_id=session.id,
                    question_id=q.id,
                    text=rng.choice(_SAMPLE_ANSWERS),
                    answered_at=now - timedelta(hours=1),
                )
            )
        if i % 50 == 0:
            await db.flush()
    await db.commit()
    logger.info(
        "load_seed_complete",
        extra={"campaign_id": campaign.id, "sessions": session_count},
    )
    return {"campaign_id": campaign.id, "script_id": script.id}


def make_session_factory():
    """async_sessionmaker, переиспользуемый по сценариям."""
    settings = get_settings()
    engine = create_async_engine(settings.effective_database_url, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def run(coro):
    """Запустить coroutine из CLI."""
    return asyncio.run(coro)
