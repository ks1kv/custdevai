"""Асинхронный доступ к PostgreSQL из bot-контейнера.

Бот переиспользует тот же async-engine и sessionmaker, что и API
(подтверждено пользователем: HTTP-прослойка ломает FR-DB-02 ACID).
Реализация совпадает с apps.api.db.session, но lru_cache отдельный —
чтобы у бота был свой пул соединений.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from apps.api.config import get_settings


@lru_cache(maxsize=1)
def get_bot_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.effective_database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


@lru_cache(maxsize=1)
def get_bot_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_bot_engine(),
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def open_session() -> AsyncIterator[AsyncSession]:
    """Контекст-менеджер на одну логическую операцию бота."""
    sessionmaker = get_bot_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
