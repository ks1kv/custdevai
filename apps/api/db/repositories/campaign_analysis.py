"""Атомарные переходы CampaignAnalysisStatus (FR-API-04, FR-RPT-07)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models import Campaign, CampaignAnalysisStatus


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


async def try_acquire_running(db: AsyncSession, campaign_id: int) -> bool:
    """Атомарно перевести analysis_status: pending|completed|failed → running.

    Защита от двойного запуска (две Celery-таски конкурируют — одна
    выиграет UPDATE, другая получит rowcount=0 и должна вернуть skipped).

    Returns:
        True если переход выполнен; False если кампания уже в running
        (другой воркер взял её первым) или вообще не существует.
    """
    stmt = (
        update(Campaign)
        .where(
            Campaign.id == campaign_id,
            Campaign.analysis_status.in_(
                [
                    CampaignAnalysisStatus.PENDING,
                    CampaignAnalysisStatus.COMPLETED,
                    CampaignAnalysisStatus.FAILED,
                ]
            ),
        )
        .values(
            analysis_status=CampaignAnalysisStatus.RUNNING,
            analysis_started_at=_utcnow(),
            analysis_completed_at=None,
            analysis_error=None,
        )
    )
    result = await db.execute(stmt)
    await db.commit()
    return (result.rowcount or 0) > 0


async def mark_completed(db: AsyncSession, campaign_id: int) -> None:
    await db.execute(
        update(Campaign)
        .where(Campaign.id == campaign_id)
        .values(
            analysis_status=CampaignAnalysisStatus.COMPLETED,
            analysis_completed_at=_utcnow(),
            analysis_error=None,
        )
    )
    await db.commit()


async def mark_failed(db: AsyncSession, campaign_id: int, *, error: str) -> None:
    """Зафиксировать неуспех; error truncate до 1024 символов (NFR-SEC-07)."""
    truncated = error[:1024] if error else None
    await db.execute(
        update(Campaign)
        .where(Campaign.id == campaign_id)
        .values(
            analysis_status=CampaignAnalysisStatus.FAILED,
            analysis_completed_at=_utcnow(),
            analysis_error=truncated,
        )
    )
    await db.commit()
