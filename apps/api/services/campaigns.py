"""Бизнес-логика кампаний (FR-API-01, FR-DB-03)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.hashing import derive_campaign_salt, random_campaign_salt
from apps.api.config import Settings
from apps.api.db.models import (
    Answer,
    Campaign,
    CampaignAnalysisStatus,
    CampaignStatus,
    InterviewSession,
    Script,
    SentimentResult,
    SessionStatus,
    Topic,
)
from apps.api.db.repositories.campaigns import CampaignRepository
from apps.api.errors import Conflict, NotFound, ValidationFailed
from apps.api.schemas.campaign import CampaignCreate, CampaignUpdate

# Допустимые переходы между статусами кампании.
_ALLOWED_TRANSITIONS = {
    CampaignStatus.DRAFT: {CampaignStatus.RUNNING, CampaignStatus.COMPLETED},
    CampaignStatus.RUNNING: {CampaignStatus.PAUSED, CampaignStatus.COMPLETED},
    CampaignStatus.PAUSED: {CampaignStatus.RUNNING, CampaignStatus.COMPLETED},
    CampaignStatus.COMPLETED: set(),
}


class CampaignService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._repo = CampaignRepository(session)

    async def _ensure_script(self, script_id: int) -> Script:
        script = await self._session.get(Script, script_id)
        if script is None:
            raise ValidationFailed("Указанный сценарий не существует.")
        return script

    async def create(self, payload: CampaignCreate, *, owner_id: int) -> Campaign:
        await self._ensure_script(payload.script_id)
        # Соль генерируется до получения id (id ещё не назначен), поэтому
        # используем CSPRNG. Деривация HKDF от мастер-соли применяется
        # ботом для воспроизводимого хеширования telegram_id (FR-DB-03).
        campaign = Campaign(
            title=payload.title,
            description=payload.description,
            script_id=payload.script_id,
            created_by_user_id=owner_id,
            status=CampaignStatus.DRAFT,
            pseudonym_salt=random_campaign_salt(),
            target_topic_count=payload.target_topic_count,
        )
        self._session.add(campaign)
        await self._session.commit()
        await self._session.refresh(campaign)
        return campaign

    async def get(self, campaign_id: int, *, owner_id: int | None) -> Campaign:
        campaign = await self._repo.get(campaign_id)
        if campaign is None:
            raise NotFound("Кампания не найдена.")
        if owner_id is not None and campaign.created_by_user_id != owner_id:
            raise NotFound("Кампания не найдена.")
        return campaign

    async def list_(
        self,
        *,
        limit: int,
        offset: int,
        owner_id: int | None,
        status_filter: CampaignStatus | None,
    ) -> tuple[list[Campaign], int]:
        return await self._repo.list_paginated(
            limit=limit, offset=offset, owner_id=owner_id, status_filter=status_filter
        )

    async def update(
        self, campaign_id: int, payload: CampaignUpdate, *, owner_id: int | None
    ) -> Campaign:
        campaign = await self.get(campaign_id, owner_id=owner_id)
        if payload.title is not None:
            campaign.title = payload.title
        if payload.description is not None:
            campaign.description = payload.description
        if payload.target_topic_count is not None:
            campaign.target_topic_count = payload.target_topic_count
        if payload.status is not None and payload.status != campaign.status:
            allowed = _ALLOWED_TRANSITIONS[campaign.status]
            if payload.status not in allowed:
                raise Conflict(
                    f"Недопустимый переход статуса кампании из {campaign.status.value} в {payload.status.value}."
                )
            campaign.status = payload.status
            now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
            if payload.status == CampaignStatus.RUNNING and campaign.started_at is None:
                campaign.started_at = now
            if payload.status == CampaignStatus.COMPLETED:
                campaign.completed_at = now
        await self._session.commit()
        await self._session.refresh(campaign)
        return campaign

    async def delete(self, campaign_id: int, *, owner_id: int | None) -> None:
        campaign = await self.get(campaign_id, owner_id=owner_id)
        # Каскад в БД (sessions/answers/sentiment_results/topics) — ON DELETE CASCADE.
        await self._repo.delete(campaign)
        await self._session.commit()

    async def _derive_salt(self, campaign_id: int) -> bytes:
        return derive_campaign_salt(
            master_salt_hex=self._settings.pseudonym_master_salt,
            campaign_id=campaign_id,
        )

    # ----- Phase 3: ML pipeline orchestration (FR-API-04, FR-RPT-07) ---------

    async def enqueue_analysis(self, campaign_id: int, *, owner_id: int | None) -> str:
        """Поставить пайплайн анализа в очередь. Возвращает task_id.

        Если кампания уже в `running` — Conflict (409). Для `completed` /
        `failed` запуск разрешён (re-run, FR-RPT-07): таска DELETE+INSERT-нет
        старые результаты.
        """
        campaign = await self.get(campaign_id, owner_id=owner_id)
        if campaign.analysis_status == CampaignAnalysisStatus.RUNNING:
            raise Conflict(
                "Анализ уже выполняется для этой кампании. Дождитесь завершения или статуса failed."
            )
        # Lazy-импорт Celery-таски, чтобы apps.api не зависел от worker-stack
        # на старте.
        from apps.worker.tasks.ml_pipeline import analyze_campaign

        async_result = analyze_campaign.delay(campaign_id)
        return str(async_result.id)

    async def get_analysis_status(
        self, campaign_id: int, *, owner_id: int | None
    ) -> dict[str, object]:
        campaign = await self.get(campaign_id, owner_id=owner_id)
        return {
            "campaign_id": campaign.id,
            "analysis_status": campaign.analysis_status.value,
            "analysis_started_at": campaign.analysis_started_at,
            "analysis_completed_at": campaign.analysis_completed_at,
            "analysis_error": campaign.analysis_error,
            "target_topic_count": campaign.target_topic_count,
        }

    async def get_summary(
        self, campaign_id: int, *, owner_id: int | None, top_n: int = 5
    ) -> dict[str, object]:
        """Лёгкая сводка для сравнения (FR-WEB-08): только агрегации.

        Возвращает метаданные кампании, счётчики сессий/ответов,
        распределение тональности и top-N тем. Без транскриптов и цитат —
        отдельно от тяжёлого load_campaign_report_context.
        """
        campaign = await self.get(campaign_id, owner_id=owner_id)

        sessions_total = (
            await self._session.scalar(
                select(func.count(InterviewSession.id)).where(
                    InterviewSession.campaign_id == campaign_id
                )
            )
            or 0
        )
        sessions_completed = (
            await self._session.scalar(
                select(func.count(InterviewSession.id)).where(
                    InterviewSession.campaign_id == campaign_id,
                    InterviewSession.status == SessionStatus.COMPLETED,
                )
            )
            or 0
        )
        answers_total = (
            await self._session.scalar(
                select(func.count(Answer.id))
                .join(InterviewSession, InterviewSession.id == Answer.session_id)
                .where(InterviewSession.campaign_id == campaign_id)
            )
            or 0
        )

        sentiment_rows = (
            await self._session.execute(
                select(SentimentResult.label, func.count(SentimentResult.id))
                .join(Answer, Answer.id == SentimentResult.answer_id)
                .join(InterviewSession, InterviewSession.id == Answer.session_id)
                .where(InterviewSession.campaign_id == campaign_id)
                .group_by(SentimentResult.label)
            )
        ).all()
        sentiment_distribution: dict[str, int] = {
            label.value: int(count) for label, count in sentiment_rows
        }

        topic_rows = (
            await self._session.execute(
                select(Topic.label, Topic.keywords, Topic.frequency_count)
                .where(Topic.campaign_id == campaign_id, Topic.is_noise.is_(False))
                .order_by(Topic.frequency_count.desc())
                .limit(top_n)
            )
        ).all()
        topics_top: list[dict[str, object]] = [
            {
                "label": label,
                "keywords": list(keywords or []),
                "frequency_count": int(freq),
            }
            for label, keywords, freq in topic_rows
        ]

        return {
            "campaign_id": campaign.id,
            "title": campaign.title,
            "description": campaign.description,
            "status": campaign.status,
            "analysis_status": campaign.analysis_status,
            "target_topic_count": campaign.target_topic_count,
            "sessions_total": int(sessions_total),
            "sessions_completed": int(sessions_completed),
            "answers_total": int(answers_total),
            "sentiment_distribution": sentiment_distribution,
            "topics_top": topics_top,
        }
