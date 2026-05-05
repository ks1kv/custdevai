"""Эндпойнты проверки готовности процесса (NFR-OPS-01)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """Проверка живости процесса. Возвращает 200, если приложение запущено."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready() -> dict[str, str]:
    """Проверка готовности обслуживать запросы.

    На Phase 1 не выполняет глубокую диагностику зависимостей —
    отвечает 200, если процесс прошёл инициализацию.
    """
    return {"status": "ready"}
