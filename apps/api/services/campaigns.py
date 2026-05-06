"""Бизнес-логика кампаний (FR-API-01, FR-DB-03)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.hashing import derive_campaign_salt, random_campaign_salt
from apps.api.config import Settings
from apps.api.db.models import Campaign, CampaignStatus, Script
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
