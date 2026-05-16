"""Integration-тест ML-пайплайна с Fake-классами (NFR-MNT-03, FR-RPT-07).

Тестируется orchestration-слой: try_acquire_running, replace_for_campaign
SentimentResult/Topic, mark_completed. Используются заглушки SentimentAnalyzer
и TopicModeler — это позволяет проверить инварианты ACID и идемпотентности
без загрузки 1.5 ГБ весов и без реального Celery-брокера.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from apps.api.config import Settings
from apps.api.db.models import (
    Answer,
    Campaign,
    CampaignAnalysisStatus,
    CampaignStatus,
    InterviewSession,
    Question,
    Script,
    SentimentLabel,
    SentimentResult,
    SessionStatus,
    User,
)
from apps.api.db.repositories.campaign_analysis import (
    mark_completed,
    mark_failed,
    try_acquire_running,
)
from apps.api.db.repositories.ml_results import (
    SentimentResultRepository,
    fetch_campaign_answer_corpus,
)
from apps.ml.base import SentimentAnalyzer, TopicModeler
from apps.ml.sentiment.schemas import SentimentInference
from apps.ml.topics.schemas import (
    SessionTopicAssignment,
    TopicModelingResult,
    TopicResult,
)


class FakeSentimentAnalyzer(SentimentAnalyzer):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def warmup(self) -> None:
        return

    def analyze_batch(self, texts: Sequence[str], *, threshold: float) -> list[SentimentInference]:
        out: list[SentimentInference] = []
        for t in texts:
            if not t.strip():
                out.append(
                    SentimentInference(
                        label=SentimentLabel.LOW_CONFIDENCE,
                        confidence=0.0,
                        is_language_error=True,
                    )
                )
                continue
            label = (
                SentimentLabel.POSITIVE
                if "хорош" in t.lower()
                else SentimentLabel.NEGATIVE
                if "плох" in t.lower()
                else SentimentLabel.NEUTRAL
            )
            out.append(SentimentInference(label=label, confidence=0.92))
        return out


class FakeTopicModeler(TopicModeler):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def warmup(self) -> None:
        return

    def fit_transform(
        self,
        texts: Sequence[str],
        *,
        session_ids: Sequence[int],
        target_topic_count: int,
    ) -> TopicModelingResult:
        topics = [
            TopicResult(
                topic_id_in_model=0,
                keywords=["продукт", "качество"],
                frequency_count=sum(1 for i in range(len(texts)) if i % 2 == 0),
                is_noise=False,
                representative_quotes=[texts[i] for i in range(len(texts)) if i % 2 == 0][:3],
            ),
            TopicResult(
                topic_id_in_model=1,
                keywords=["цена", "доставка"],
                frequency_count=sum(1 for i in range(len(texts)) if i % 2 == 1),
                is_noise=False,
                representative_quotes=[texts[i] for i in range(len(texts)) if i % 2 == 1][:3],
            ),
        ]
        assignments = [
            SessionTopicAssignment(
                session_id=sid,
                topic_id_in_model=(0 if i % 2 == 0 else 1),
                representative_quote=texts[i] if i < 3 else None,
            )
            for i, sid in enumerate(session_ids)
        ]
        return TopicModelingResult(topics=topics, assignments=assignments)


def _utcnaive() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


@pytest_asyncio.fixture
async def seeded_campaign_with_answers(db_session) -> dict[str, int]:
    user = User(email="r@m.x", password_hash="$2b$12$" + "a" * 53)
    db_session.add(user)
    await db_session.flush()

    script = Script(title="S", created_by_user_id=user.id)
    db_session.add(script)
    await db_session.flush()
    question = Question(script_id=script.id, order_index=0, text="Какой ваш отзыв?")
    db_session.add(question)
    await db_session.flush()

    campaign = Campaign(
        title="К3",
        script_id=script.id,
        created_by_user_id=user.id,
        status=CampaignStatus.COMPLETED,
        pseudonym_salt=b"\x00" * 32,
        target_topic_count=10,
    )
    db_session.add(campaign)
    await db_session.flush()

    answer_ids: list[int] = []
    for i, text in enumerate(
        ["хорошо работает", "плохо доставляют", "так себе", "хорошее качество"]
    ):
        s = InterviewSession(
            campaign_id=campaign.id,
            telegram_id_hash=bytes([i + 1]) + b"\x00" * 31,
            status=SessionStatus.COMPLETED,
            progress_count=1,
        )
        db_session.add(s)
        await db_session.flush()
        a = Answer(
            session_id=s.id,
            question_id=question.id,
            text=text,
            answered_at=_utcnaive(),
        )
        db_session.add(a)
        await db_session.flush()
        answer_ids.append(a.id)
    await db_session.commit()
    return {
        "campaign_id": campaign.id,
        "user_id": user.id,
        "answer_ids": answer_ids,
    }


@pytest.mark.asyncio
async def test_try_acquire_running_atomic_lock(db_session, seeded_campaign_with_answers) -> None:
    cid = seeded_campaign_with_answers["campaign_id"]
    assert await try_acquire_running(db_session, cid) is True

    # Параллельный запуск (имитация другой Celery-таски) — должен получить False.
    assert await try_acquire_running(db_session, cid) is False

    fresh = await db_session.get(Campaign, cid)
    assert fresh is not None and fresh.analysis_status == CampaignAnalysisStatus.RUNNING


@pytest.mark.asyncio
async def test_full_pipeline_inserts_results(
    db_session, seeded_campaign_with_answers, settings
) -> None:
    """E2E на уровне сервисов с FakeAnalyzer/FakeModeler."""
    cid = seeded_campaign_with_answers["campaign_id"]

    await try_acquire_running(db_session, cid)
    answers, _ = await fetch_campaign_answer_corpus(db_session, cid)
    texts = [a.text for a in answers]
    session_ids = [a.session_id for a in answers]

    analyzer = FakeSentimentAnalyzer(settings)
    modeler = FakeTopicModeler(settings)

    sentiment_inferences = analyzer.analyze_batch(texts, threshold=0.5)
    sentiment_repo = SentimentResultRepository(db_session)
    inserted = await sentiment_repo.replace_for_campaign(
        cid, answers=answers, inferences=sentiment_inferences
    )
    await db_session.commit()
    assert inserted == 4

    # Topic-таблицу пропускаем (ARRAY на SQLite). Проверяем DTO от FakeModeler.
    topic_result = modeler.fit_transform(texts, session_ids=session_ids, target_topic_count=10)
    assert len(topic_result.topics) == 2

    await mark_completed(db_session, cid)

    fresh = await db_session.get(Campaign, cid)
    assert fresh is not None
    assert fresh.analysis_status == CampaignAnalysisStatus.COMPLETED
    assert fresh.analysis_completed_at is not None

    sentiment_rows = list(
        (
            await db_session.execute(
                select(SentimentResult).where(
                    SentimentResult.answer_id.in_(seeded_campaign_with_answers["answer_ids"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(sentiment_rows) == 4


@pytest.mark.asyncio
async def test_re_run_replaces_existing_results(
    db_session, seeded_campaign_with_answers, settings
) -> None:
    """FR-RPT-07: повторный запуск анализа удаляет старые строки и
    вставляет новые без дублей."""
    cid = seeded_campaign_with_answers["campaign_id"]
    answers, _ = await fetch_campaign_answer_corpus(db_session, cid)
    texts = [a.text for a in answers]

    analyzer = FakeSentimentAnalyzer(settings)

    # Первый прогон (только sentiment — topics требует ARRAY/PG).
    sentiment_repo = SentimentResultRepository(db_session)
    await sentiment_repo.replace_for_campaign(
        cid, answers=answers, inferences=analyzer.analyze_batch(texts, threshold=0.5)
    )
    await db_session.commit()

    sentiment_first = list(
        (
            await db_session.execute(
                select(SentimentResult).where(
                    SentimentResult.answer_id.in_(seeded_campaign_with_answers["answer_ids"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(sentiment_first) == 4

    # Re-run: должно удалить и вставить заново — счётчик НЕ удваивается.
    await sentiment_repo.replace_for_campaign(
        cid, answers=answers, inferences=analyzer.analyze_batch(texts, threshold=0.5)
    )
    await db_session.commit()

    sentiment_after = list(
        (
            await db_session.execute(
                select(SentimentResult).where(
                    SentimentResult.answer_id.in_(seeded_campaign_with_answers["answer_ids"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(sentiment_after) == 4  # дубля нет


@pytest.mark.asyncio
async def test_mark_failed_stores_truncated_error(db_session, seeded_campaign_with_answers) -> None:
    cid = seeded_campaign_with_answers["campaign_id"]
    long_msg = "x" * 2000
    await mark_failed(db_session, cid, error=long_msg)
    fresh = await db_session.get(Campaign, cid)
    assert fresh is not None
    assert fresh.analysis_status == CampaignAnalysisStatus.FAILED
    assert fresh.analysis_error is not None
    assert len(fresh.analysis_error) <= 1024


@pytest.mark.asyncio
async def test_release_running_for_retry_allows_reacquire(
    db_session, seeded_campaign_with_answers
) -> None:
    """release_running_for_retry возвращает RUNNING → PENDING и снимает
    залипание, чтобы следующий retry мог try_acquire_running."""
    from apps.api.db.repositories.campaign_analysis import release_running_for_retry

    cid = seeded_campaign_with_answers["campaign_id"]
    # 1. Захватываем RUNNING как обычно.
    assert await try_acquire_running(db_session, cid) is True
    # 2. Повторный acquire не проходит — статус уже RUNNING.
    assert await try_acquire_running(db_session, cid) is False
    # 3. Освобождаем для retry.
    assert await release_running_for_retry(db_session, cid) is True
    fresh = await db_session.get(Campaign, cid)
    assert fresh is not None
    assert fresh.analysis_status == CampaignAnalysisStatus.PENDING
    assert fresh.analysis_started_at is None
    # 4. Теперь acquire снова проходит.
    assert await try_acquire_running(db_session, cid) is True

    # 5. Если статус не RUNNING — release_running_for_retry — no-op.
    await mark_completed(db_session, cid)
    assert await release_running_for_retry(db_session, cid) is False


@pytest.mark.asyncio
async def test_sweep_stuck_running_marks_old_as_failed(
    db_session, seeded_campaign_with_answers
) -> None:
    """sweep_stuck_running переводит зависшие RUNNING (started_at > N мин назад)
    в FAILED; повторный вызов — no-op."""
    from datetime import datetime, timedelta, timezone

    from apps.api.db.repositories.campaign_analysis import sweep_stuck_running

    cid = seeded_campaign_with_answers["campaign_id"]
    assert await try_acquire_running(db_session, cid) is True

    fresh = await db_session.get(Campaign, cid)
    assert fresh is not None
    fresh.analysis_started_at = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(
        minutes=30
    )
    await db_session.commit()

    swept = await sweep_stuck_running(db_session, older_than=timedelta(minutes=20))
    assert swept == [cid]
    refreshed = await db_session.get(Campaign, cid)
    assert refreshed is not None
    assert refreshed.analysis_status == CampaignAnalysisStatus.FAILED
    assert refreshed.analysis_error and "прерван" in refreshed.analysis_error

    again = await sweep_stuck_running(db_session, older_than=timedelta(minutes=20))
    assert again == []


@pytest.mark.asyncio
async def test_sweep_stuck_running_skips_fresh(db_session, seeded_campaign_with_answers) -> None:
    """Свежий RUNNING (started_at = сейчас) не должен попадать в зачистку."""
    from datetime import timedelta

    from apps.api.db.repositories.campaign_analysis import sweep_stuck_running

    cid = seeded_campaign_with_answers["campaign_id"]
    assert await try_acquire_running(db_session, cid) is True

    swept = await sweep_stuck_running(db_session, older_than=timedelta(minutes=20))
    assert swept == []
    fresh = await db_session.get(Campaign, cid)
    assert fresh is not None
    assert fresh.analysis_status == CampaignAnalysisStatus.RUNNING


@pytest.mark.asyncio
async def test_language_error_skipped_in_sentiment_results(
    db_session, seeded_campaign_with_answers, settings
) -> None:
    """FR-SENT-06: SentimentInference(is_language_error=True) не пишется в БД."""
    cid = seeded_campaign_with_answers["campaign_id"]
    answers, _ = await fetch_campaign_answer_corpus(db_session, cid)

    inferences: list[SentimentInference] = [
        SentimentInference(label=SentimentLabel.POSITIVE, confidence=0.9),
        SentimentInference(
            label=SentimentLabel.LOW_CONFIDENCE, confidence=0.0, is_language_error=True
        ),
        SentimentInference(label=SentimentLabel.NEUTRAL, confidence=0.7),
        SentimentInference(label=SentimentLabel.NEGATIVE, confidence=0.85),
    ]
    repo = SentimentResultRepository(db_session)
    inserted = await repo.replace_for_campaign(cid, answers=answers, inferences=inferences)
    await db_session.commit()
    assert inserted == 3  # один пропущен из-за is_language_error
