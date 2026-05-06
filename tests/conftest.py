"""Общие фикстуры тестов CustDevAI."""

from __future__ import annotations

import os
import secrets

import pytest

# Базовый набор переменных окружения для тестов. Гарантирует, что
# Settings(BaseSettings) валидируется без файла .env.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("JWT_SECRET", secrets.token_hex(32))
os.environ.setdefault("PSEUDONYM_MASTER_SALT", secrets.token_hex(32))
os.environ.setdefault("BCRYPT_COST_FACTOR", "12")


@pytest.fixture
def settings():
    """Singleton-настройки, очищенные перед каждым тестом."""
    from apps.api.config import get_settings

    get_settings.cache_clear()
    return get_settings()


class FakeAsyncRedis:
    """In-memory заглушка async-redis для unit-тестов.

    Поддерживает incr/expire/set(ex)/exists/delete — достаточно для
    BruteForceGuard и Token*Store. TTL не реализован в реальном времени
    (тесты не проверяют истечение, только наличие/отсутствие ключа).
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._ttl: dict[str, int] = {}

    async def incr(self, name: str) -> int:
        cur = int(self._store.get(name, "0")) + 1
        self._store[name] = str(cur)
        return cur

    async def expire(self, name: str, time: int) -> bool:
        if name in self._store:
            self._ttl[name] = time
            return True
        return False

    async def set(
        self, name: str, value: str, ex: int | None = None, nx: bool = False
    ) -> bool | None:
        if nx and name in self._store:
            return None
        self._store[name] = value
        if ex is not None:
            self._ttl[name] = ex
        return True

    async def exists(self, *names: str) -> int:
        return sum(1 for n in names if n in self._store)

    async def delete(self, *names: str) -> int:
        count = 0
        for n in names:
            if n in self._store:
                del self._store[n]
                self._ttl.pop(n, None)
                count += 1
        return count


@pytest.fixture
def fake_redis() -> FakeAsyncRedis:
    return FakeAsyncRedis()
