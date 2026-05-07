"""Репозиторий записей согласия (FR-BOT-01)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models import Consent


class ConsentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_session(self, session_id: int) -> Consent | None:
        stmt = select(Consent).where(Consent.session_id == session_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self,
        *,
        session_id: int,
        ip_address_hash: bytes | None,
        consent_version: str,
    ) -> bool:
        """Записать согласие. UNIQUE на session_id защищает от двойного нажатия.

        Returns:
            True, если новая запись создана; False, если уже была (idempotent).
        """
        stmt = (
            pg_insert(Consent)
            .values(
                session_id=session_id,
                ip_address_hash=ip_address_hash,
                consent_version=consent_version,
            )
            .on_conflict_do_nothing(index_elements=["session_id"])
            .returning(Consent.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
