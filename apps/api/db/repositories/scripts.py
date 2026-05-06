"""Репозиторий сценариев и вопросов."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models import Campaign, Question, Script


class ScriptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, script_id: int) -> Script | None:
        return await self._session.get(Script, script_id)

    async def list_paginated(
        self,
        *,
        limit: int,
        offset: int,
        owner_id: int | None,
    ) -> tuple[list[Script], int]:
        base = select(Script)
        if owner_id is not None:
            base = base.where(Script.created_by_user_id == owner_id)
        count_stmt = select(func.count()).select_from(base.subquery())
        items_stmt = base.order_by(Script.id.desc()).limit(limit).offset(offset)
        total = (await self._session.execute(count_stmt)).scalar_one()
        result = await self._session.execute(items_stmt)
        return list(result.scalars().all()), int(total)

    async def has_running_campaign(self, script_id: int) -> bool:
        from apps.api.db.models import CampaignStatus

        stmt = select(func.count()).where(
            Campaign.script_id == script_id, Campaign.status == CampaignStatus.RUNNING
        )
        return (await self._session.execute(stmt)).scalar_one() > 0

    async def has_any_campaign(self, script_id: int) -> bool:
        stmt = select(func.count()).where(Campaign.script_id == script_id)
        return (await self._session.execute(stmt)).scalar_one() > 0

    async def add(self, script: Script) -> None:
        self._session.add(script)

    async def add_question(self, question: Question) -> None:
        self._session.add(question)

    async def delete(self, script: Script) -> None:
        await self._session.delete(script)

    async def get_question(self, question_id: int) -> Question | None:
        return await self._session.get(Question, question_id)

    async def delete_question(self, question: Question) -> None:
        await self._session.delete(question)
