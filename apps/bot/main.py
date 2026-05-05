"""Заглушка Telegram-бота на Phase 1.

Реальная диалоговая логика на aiogram 3.x будет реализована в Phase 2.
Контейнер просто пишет маркер в лог и держится в живых, чтобы
docker-compose не падал.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("[bot] not yet implemented — будет добавлено в Phase 2 (FR-BOT-*)")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
