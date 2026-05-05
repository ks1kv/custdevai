"""Защита от брутфорса логина и deny-list для отозванных токенов.

Хранилище — Redis (FR-AUTH-08, NFR-SEC-05). Алгоритм:
- инкремент `bf:{ip}` с TTL 600 сек на каждую неуспешную попытку входа;
- при достижении 5 попыток — установить `bf:lock:{ip}` с TTL 900 сек;
- при последующих запросах middleware проверяет `bf:lock:{ip}` до bcrypt.

Отозванные jti записываются ключом `revoked:{jti}` с TTL = оставшееся
время жизни токена. Любая проверка `is_revoked(jti)` возвращает True
до истечения этого TTL.
"""

from __future__ import annotations

from typing import Protocol

from apps.api.config import Settings


class AsyncRedisLike(Protocol):
    """Минимальный контракт async-redis-клиента, нужный модулю.

    Достаточен для unit-тестов с поддельной реализацией и для
    реального redis.asyncio.Redis в продакшене.
    """

    async def incr(self, name: str) -> int: ...
    async def expire(self, name: str, time: int) -> bool: ...
    async def set(
        self, name: str, value: str, ex: int | None = None, nx: bool = False
    ) -> bool | None: ...
    async def exists(self, *names: str) -> int: ...
    async def delete(self, *names: str) -> int: ...


class BruteForceGuard:
    """Реализация политики 5/10/15 поверх произвольного async-redis-клиента."""

    def __init__(self, redis: AsyncRedisLike, settings: Settings) -> None:
        self._redis = redis
        self._max = settings.bruteforce_max_attempts
        self._window = settings.bruteforce_window_seconds
        self._lock_ttl = settings.bruteforce_lock_seconds

    @staticmethod
    def _counter_key(ip: str) -> str:
        return f"bf:{ip}"

    @staticmethod
    def _lock_key(ip: str) -> str:
        return f"bf:lock:{ip}"

    async def is_locked(self, ip: str) -> bool:
        return bool(await self._redis.exists(self._lock_key(ip)))

    async def register_failure(self, ip: str) -> bool:
        """Зафиксировать неуспешную попытку. Возвращает True, если IP теперь заблокирован."""
        count = await self._redis.incr(self._counter_key(ip))
        if count == 1:
            await self._redis.expire(self._counter_key(ip), self._window)
        if count >= self._max:
            await self._redis.set(self._lock_key(ip), "1", ex=self._lock_ttl)
            await self._redis.delete(self._counter_key(ip))
            return True
        return False

    async def reset(self, ip: str) -> None:
        """Сбросить счётчик попыток после успешного входа."""
        await self._redis.delete(self._counter_key(ip), self._lock_key(ip))


class TokenRevocationStore:
    """Deny-list для отозванных jti access- и refresh-токенов."""

    def __init__(self, redis: AsyncRedisLike) -> None:
        self._redis = redis

    @staticmethod
    def _key(jti: str) -> str:
        return f"revoked:{jti}"

    async def revoke(self, jti: str, *, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        await self._redis.set(self._key(jti), "1", ex=ttl_seconds)

    async def is_revoked(self, jti: str) -> bool:
        return bool(await self._redis.exists(self._key(jti)))


class RefreshTokenStore:
    """Whitelist активных refresh-токенов: храним только не отозванные jti.

    Пара (user_id, jti) допустима, если ключ `refresh:{jti}` существует и его
    значение совпадает с user_id. При logout/refresh ключ удаляется и jti
    дополнительно попадает в TokenRevocationStore (двойная защита).
    """

    def __init__(self, redis: AsyncRedisLike) -> None:
        self._redis = redis

    @staticmethod
    def _key(jti: str) -> str:
        return f"refresh:{jti}"

    async def remember(self, jti: str, user_id: int, *, ttl_seconds: int) -> None:
        await self._redis.set(self._key(jti), str(user_id), ex=ttl_seconds)

    async def consume(self, jti: str) -> bool:
        """Удалить jti из whitelist. True если ключ существовал."""
        deleted = await self._redis.delete(self._key(jti))
        return bool(deleted)
