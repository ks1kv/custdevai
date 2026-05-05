"""Singleton-фабрика async-redis-клиента."""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis, from_url

from apps.api.config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    """Async-клиент Redis, переиспользуемый между запросами."""
    settings = get_settings()
    return from_url(settings.effective_redis_url, decode_responses=True)
