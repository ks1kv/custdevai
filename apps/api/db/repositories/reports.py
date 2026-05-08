"""Репозиторий метаданных отчётов."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models import Report, ReportFormat


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, report_id: int) -> Report | None:
        return await self._session.get(Report, report_id)

    async def add(self, report: Report) -> None:
        self._session.add(report)

    async def list_for_campaign(
        self,
        campaign_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Report], int]:
        base = select(Report).where(Report.campaign_id == campaign_id)
        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        items_stmt = base.order_by(Report.generated_at.desc()).limit(limit).offset(offset)
        items = (await self._session.execute(items_stmt)).scalars().all()
        return items, int(total)

    async def latest_for_campaign(
        self, campaign_id: int, *, fmt: ReportFormat
    ) -> Report | None:
        stmt = (
            select(Report)
            .where(Report.campaign_id == campaign_id, Report.format == fmt)
            .order_by(Report.generated_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
