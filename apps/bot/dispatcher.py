"""Сборка aiogram Dispatcher с RedisStorage и FSM-роутерами (FR-BOT-05)."""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from redis.asyncio import Redis

# Префикс ключей в Redis: bot_fsm:user:{user_id}:state и :data.
# Изолирует FSM-данные от других подсистем (refresh-tokens, brute-force-counters).
FSM_KEY_PREFIX = "bot_fsm"


def build_redis_storage(redis_url: str) -> RedisStorage:
    """Создать RedisStorage поверх существующего Redis-контейнера.

    state_ttl=48h гарантирует, что брошенная сессия не висит в памяти
    бесконечно (FR-BOT-05). Реальная очистка статусов sessions в БД —
    задача sweeper-а Phase 5.
    """
    redis = Redis.from_url(redis_url, decode_responses=True)
    key_builder = DefaultKeyBuilder(prefix=FSM_KEY_PREFIX)
    return RedisStorage(redis=redis, key_builder=key_builder, state_ttl=48 * 60 * 60)


def build_dispatcher(*, storage: BaseStorage) -> Dispatcher:
    """Собрать Dispatcher с подключёнными хэндлерами всех роутеров.

    Импорт роутеров — внутри функции, чтобы избежать циклов при первичной
    инициализации (handler-ы импортируют сервисы, которые тянут БД).
    """
    from apps.bot.handlers import consent, interview, reject, start

    dp = Dispatcher(storage=storage)
    # Порядок имеет значение: команды (start/stop) проверяются раньше
    # текстовых ответов; reject-роутер ловит non-text последним.
    dp.include_router(start.router)
    dp.include_router(consent.router)
    dp.include_router(interview.router)
    dp.include_router(reject.router)
    return dp
