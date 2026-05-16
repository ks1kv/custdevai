"""Атомарные переходы CampaignAnalysisStatus (FR-API-04, FR-RPT-07)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
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


async def release_running_for_retry(db: AsyncSession, campaign_id: int) -> bool:
    """Освободить статус RUNNING обратно в PENDING для следующего retry.

    Вызывается из except-блока ml-таски ДО `raise`, если retry-аттемптов
    ещё осталось. Без этого следующий запуск увидит RUNNING (выставленный
    нами же на предыдущей попытке), `try_acquire_running` вернёт False и
    отдаст «skipped» как успех — кампания залипнет в RUNNING навсегда
    (см. лог 2026-05-16 21:43..21:45 — это и наблюдалось на проде).
    """
    stmt = (
        update(Campaign)
        .where(
            Campaign.id == campaign_id,
            Campaign.analysis_status == CampaignAnalysisStatus.RUNNING,
        )
        .values(
            analysis_status=CampaignAnalysisStatus.PENDING,
            analysis_started_at=None,
        )
    )
    result = await db.execute(stmt)
    await db.commit()
    return (result.rowcount or 0) > 0


async def sweep_stuck_running(db: AsyncSession, *, older_than: timedelta) -> list[int]:
    """Зачистить «зависшие» RUNNING-кампании старше `older_than`.

    Защита от случая, когда воркер был убит хардом (OOM, SIGKILL) и
    не успел release_running_for_retry / mark_failed: периодическая
    таска через какое-то время найдёт такие кампании и пометит FAILED,
    чтобы аналитик мог перезапустить анализ из SPA.
    """
    cutoff = _utcnow() - older_than
    rows = (
        (
            await db.execute(
                select(Campaign.id).where(
                    Campaign.analysis_status == CampaignAnalysisStatus.RUNNING,
                    Campaign.analysis_started_at.is_not(None),
                    Campaign.analysis_started_at < cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    await db.execute(
        update(Campaign)
        .where(Campaign.id.in_(rows))
        .values(
            analysis_status=CampaignAnalysisStatus.FAILED,
            analysis_completed_at=_utcnow(),
            analysis_error="Анализ был прерван — воркер не завершил задачу вовремя. "
            "Запустите анализ повторно.",
        )
    )
    await db.commit()
    return list(rows)
