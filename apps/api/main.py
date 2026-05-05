"""FastAPI app factory для CustDevAI.

Точка входа `app` собирается через `create_app()`, чтобы конфигурация и
зависимости подменялись в тестах через `dependency_overrides`. Маршруты
подключаются с префиксом `/api/v1` (FR-API-06).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from fastapi import APIRouter

from apps.api.auth.router import router as auth_router
from apps.api.config import Settings, get_settings
from apps.api.errors import register_error_handlers
from apps.api.routers import health, users

API_V1_PREFIX = "/api/v1"

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Собрать ASGI-приложение FastAPI.

    Args:
        settings: Опциональная подмена конфигурации (для тестов).

    Returns:
        Сконфигурированный FastAPI-инстанс.
    """
    cfg = settings or get_settings()
    logging.basicConfig(level=cfg.log_level)

    app = FastAPI(
        title="CustDevAI API",
        version="0.1.0",
        description="REST API для системы автоматизации Customer Development.",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )
    app.state.settings = cfg
    register_error_handlers(app)
    app.include_router(health.router)

    api_v1 = APIRouter(prefix=API_V1_PREFIX)
    api_v1.include_router(auth_router)
    api_v1.include_router(users.router)
    app.include_router(api_v1)
    return app


app = create_app()
