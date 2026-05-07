"""analyze_campaign — Celery-задача оркестрации ML-пайплайна.

Триггеры:
  * Автоматический — apps/bot/services/notify_service.py после закрытия
    последней сессии кампании (FR-API-04).
  * Ручной — POST /api/v1/campaigns/{id}/analyze (FR-RPT-07).

Шаги (каждый в отдельной БД-транзакции):
  1. Atomic status PENDING|COMPLETED|FAILED → RUNNING. Двойной запуск
     отсекается на уровне SQL (try_acquire_running rowcount==0 → skip).
  2. log_pipeline_start с фиксированными seed-значениями (FR-SENT-04,
     FR-TOP-07, NFR-COR-01).
  3. set_global_seeds(SENTIMENT_RANDOM_SEED).
  4. Sentiment-analysis по всем ответам кампании; DELETE+INSERT для
     FR-RPT-07 (re-run cleanup).
  5. Topic-modeling по тем же текстам с target_topic_count из Campaign;
     DELETE+INSERT для FR-RPT-07.
  6. mark_completed.
  7. Триггер второго push: notify_researcher_analysis_ready.

При исключении на любом шаге Celery retry до 3 раз с экспоненциальной
задержкой (autoretry_for=Exception). После последней неудачи —
mark_failed с обрезанным сообщением. Аналитик может перезапустить
через POST /analyze.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.config import Settings, get_settings
from apps.api.db.models import Campaign, SessionStatus
from apps.api.db.repositories.campaign_analysis import (
    mark_completed,
    mark_failed,
    try_acquire_running,
)
from apps.api.db.repositories.ml_results import (
    SentimentResultRepository,
    TopicResultRepository,
    fetch_campaign_answer_corpus,
)
from apps.ml.base import SentimentAnalyzer, TopicModeler
from apps.ml.seeds import set_global_seeds
from apps.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# Lazy DI: можно подменить в тестах через set_analyzers().
_analyzer_factory: Any | None = None
_modeler_factory: Any | None = None


def set_analyzers(
    *,
    analyzer_factory: Any | None,
    modeler_factory: Any | None,
) -> None:
    """Подменить фабрики ML-модулей (NFR-MNT-03). Используется в тестах."""
    global _analyzer_factory, _modeler_factory
    _analyzer_factory = analyzer_factory
    _modeler_factory = modeler_factory


def _resolve_analyzer(settings: Settings) -> SentimentAnalyzer:
    if _analyzer_factory is not None:
        return _analyzer_factory(settings)
    from apps.ml.sentiment.analyzer import RuBERTSentimentAnalyzer

    return RuBERTSentimentAnalyzer(settings)


def _resolve_modeler(settings: Settings) -> TopicModeler:
    if _modeler_factory is not None:
        return _modeler_factory(settings)
    from apps.ml.topics.modeler import BERTopicModeler

    return BERTopicModeler(settings)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    name="ml.analyze_campaign",
)
def analyze_campaign(self: Any, campaign_id: int) -> dict[str, Any]:
    """Sync-обёртка вокруг async-пайплайна (Celery worker — синхронный)."""
    return asyncio.run(_analyze_campaign_async(campaign_id, self.request.retries))


async def _analyze_campaign_async(campaign_id: int, retry_attempt: int) -> dict[str, Any]:
    settings = get_settings()
    engine = create_async_engine(settings.effective_database_url, future=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    try:
        # 1. Atomic переход в RUNNING.
        async with sessionmaker() as db:
            acquired = await try_acquire_running(db, campaign_id)
        if not acquired:
            logger.info(
                "ml_pipeline_skipped",
                extra={"campaign_id": campaign_id, "reason": "already_running"},
            )
            return {"campaign_id": campaign_id, "skipped": True}

        # 2-3. Логируем старт + фиксируем seeds.
        logger.info(
            "ml_pipeline_start",
            extra={
                "campaign_id": campaign_id,
                "sentiment_seed": settings.sentiment_random_seed,
                "topic_seed": settings.topic_random_seed,
                "retry_attempt": retry_attempt,
            },
        )
        set_global_seeds(settings.sentiment_random_seed)

        async with sessionmaker() as db:
            answers, sessions = await fetch_campaign_answer_corpus(db, campaign_id)
            campaign = await db.get(Campaign, campaign_id)
            if campaign is None:
                raise RuntimeError(f"Кампания {campaign_id} не найдена.")
            target_topic_count = campaign.target_topic_count

        if not answers:
            # Кампания без ответов — анализ нечего делать; просто завершаем.
            async with sessionmaker() as db:
                await mark_completed(db, campaign_id)
            return {
                "campaign_id": campaign_id,
                "skipped": False,
                "answers": 0,
                "topics": 0,
            }

        # 4. Sentiment в отдельной транзакции.
        analyzer = _resolve_analyzer(settings)
        analyzer.warmup()
        texts = [a.text for a in answers]
        sentiment_inferences = analyzer.analyze_batch(
            texts, threshold=settings.sentiment_confidence_threshold
        )

        async with sessionmaker() as db:
            sentiment_repo = SentimentResultRepository(db)
            sentiment_inserted = await sentiment_repo.replace_for_campaign(
                campaign_id, answers=answers, inferences=sentiment_inferences
            )
            await db.commit()

        # 5. Topics в отдельной транзакции.
        # Только не-шумовые тексты + сессии для seed-стабильной выборки.
        # На вход BERTopic подаются ответы целиком — кластеризация по семантике.
        modeler = _resolve_modeler(settings)
        modeler.warmup()
        topic_result = modeler.fit_transform(
            texts,
            session_ids=[a.session_id for a in answers],
            target_topic_count=target_topic_count,
        )

        async with sessionmaker() as db:
            topic_repo = TopicResultRepository(db)
            await topic_repo.replace_for_campaign(campaign_id, topic_result)
            await db.commit()

        # 6. mark completed.
        async with sessionmaker() as db:
            await mark_completed(db, campaign_id)

        # 7. Второй push (FR-BOT-09 закрытие). Не блокирующий — ошибка
        # доставки не должна откатывать факт успешного анализа.
        try:
            from apps.bot.services.notify_service import (
                notify_researcher_analysis_ready,
            )

            async with sessionmaker() as db:
                await notify_researcher_analysis_ready(
                    db,
                    campaign_id=campaign_id,
                    topics_count=len([t for t in topic_result.topics if not t.is_noise]),
                    sentiment_inserted=sentiment_inserted,
                )
        except Exception:
            logger.exception("notify_researcher_analysis_ready failed (non-fatal)")

        # Подсчёт активных сессий — для structured-лога.
        active_left = sum(1 for s in sessions if s.status == SessionStatus.ACTIVE)
        logger.info(
            "ml_pipeline_completed",
            extra={
                "campaign_id": campaign_id,
                "answers": len(answers),
                "sentiment_inserted": sentiment_inserted,
                "topics_total": len(topic_result.topics),
                "active_sessions_remaining": active_left,
            },
        )
        return {
            "campaign_id": campaign_id,
            "skipped": False,
            "answers": len(answers),
            "sentiment_inserted": sentiment_inserted,
            "topics": len(topic_result.topics),
        }

    except Exception as exc:
        # Если ретраи исчерпаны — фиксируем failed; иначе Celery сам
        # повторит вызов через autoretry_for.
        if retry_attempt >= 2:  # последний (3-й) запуск
            try:
                async with sessionmaker() as db:
                    await mark_failed(db, campaign_id, error=str(exc))
            except Exception:
                logger.exception("mark_failed itself failed for campaign_id=%s", campaign_id)
        raise
    finally:
        await engine.dispose()
