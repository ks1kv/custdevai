"""Запись согласия респондента (FR-BOT-01, NFR-SEC-08)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.repositories.consents import ConsentRepository


async def record_consent(
    db: AsyncSession,
    *,
    session_id: int,
    consent_version: str,
    ip_address_hash: bytes | None = None,
) -> bool:
    """Сохранить согласие. UNIQUE на session_id защищает от двойного нажатия."""
    repo = ConsentRepository(db)
    is_new = await repo.upsert(
        session_id=session_id,
        ip_address_hash=ip_address_hash,
        consent_version=consent_version,
    )
    await db.commit()
    return is_new
