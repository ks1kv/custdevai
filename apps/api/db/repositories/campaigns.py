"""Репозиторий кампаний."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models import Campaign, CampaignStatus


class CampaignRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, campaign_id: int) -> Campaign | None:
        return await self._session.get(Campaign, campaign_id)

    async def list_paginated(
        self,
        *,
        limit: int,
        offset: int,
        owner_id: int | None,
        status_filter: CampaignStatus | None,
    ) -> tuple[list[Campaign], int]:
        base = select(Campaign)
        if owner_id is not None:
            base = base.where(Campaign.created_by_user_id == owner_id)
        if status_filter is not None:
            base = base.where(Campaign.status == status_filter)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        items_stmt = base.order_by(Campaign.id.desc()).limit(limit).offset(offset)
        result = await self._session.execute(items_stmt)
        return list(result.scalars().all()), int(total)

    async def add(self, campaign: Campaign) -> None:
        self._session.add(campaign)

    async def delete(self, campaign: Campaign) -> None:
        await self._session.delete(campaign)

    async def get_running_for_invitation(self, campaign_id: int) -> Campaign | None:
        """Возвращает кампанию, только если она в статусе RUNNING (FR-BOT-01)."""
        stmt = select(Campaign).where(
            Campaign.id == campaign_id, Campaign.status == CampaignStatus.RUNNING
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
