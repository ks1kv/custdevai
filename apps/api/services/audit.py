"""Сервис записи событий аудита (FR-DB-05, FR-AUTH-07)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models import AuditAction, AuditLog


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        action: AuditAction,
        *,
        user_id: int | None = None,
        target_user_id: int | None = None,
        campaign_id: int | None = None,
        ip_address: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            action=action,
            user_id=user_id,
            target_user_id=target_user_id,
            campaign_id=campaign_id,
            ip_address=ip_address,
            details=details,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry
