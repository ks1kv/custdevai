"""Stand-alone лог-маркер для worker-контейнера на Phase 1.

Сам Celery-worker запускается командой `celery -A apps.worker.celery_app worker`
из docker/worker.Dockerfile. Этот модуль используется при ручной диагностике.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info(
        "[worker] not yet implemented — Celery-задачи добавляются в Phase 3 (FR-SENT-*, FR-TOP-*)"
    )
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
