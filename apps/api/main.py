"""FastAPI app factory для CustDevAI.

Точка входа `app` собирается через `create_app()`, чтобы конфигурация и
зависимости подменялись в тестах через `dependency_overrides`. Маршруты
подключаются с префиксом `/api/v1` (FR-API-06).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse

from apps.api.auth.rbac import Role
from apps.api.auth.router import router as auth_router
from apps.api.config import Settings, get_settings
from apps.api.deps import CurrentUser, require_roles
from apps.api.errors import register_error_handlers
from apps.api.middleware import register_middleware
from apps.api.routers import admin, campaigns, health, reports, scripts, users, webhook

API_V1_PREFIX = "/api/v1"

logger = logging.getLogger(__name__)


def _register_protected_docs(app: FastAPI) -> None:
    """Заменить публичные /api/docs и /api/openapi.json на JWT-защищённые
    эквиваленты (FR-API-07: документация доступна только аутентифицированным).

    Доступ к OpenAPI-схеме разрешён любому из четырёх ролей RBAC, чтобы
    исследователи и аналитики могли пользоваться Swagger UI.
    """

    docs_reader = require_roles(Role.ADMIN, Role.RESEARCHER, Role.ANALYST, Role.RESPONDENT)

    @app.get("/api/openapi.json", include_in_schema=False)
    async def protected_openapi(_: CurrentUser = Depends(docs_reader)) -> JSONResponse:
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        return JSONResponse(schema)

    @app.get("/api/docs", include_in_schema=False)
    async def protected_swagger_ui(_: CurrentUser = Depends(docs_reader)) -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url="/api/openapi.json",
            title=f"{app.title} — Swagger UI",
        )

    @app.get("/api/redoc", include_in_schema=False)
    async def protected_redoc(_: CurrentUser = Depends(docs_reader)) -> HTMLResponse:
        return get_redoc_html(
            openapi_url="/api/openapi.json",
            title=f"{app.title} — ReDoc",
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Собрать ASGI-приложение FastAPI."""
    cfg = settings or get_settings()
    logging.basicConfig(level=cfg.log_level)

    # docs_url/redoc_url/openapi_url = None отключает встроенные публичные
    # эндпойнты — далее мы регистрируем JWT-защищённые аналоги.
    app = FastAPI(
        title="CustDevAI API",
        version="0.1.0",
        description="REST API для системы автоматизации Customer Development.",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = cfg
    register_error_handlers(app)
    register_middleware(app, cfg)
    app.include_router(health.router)

    api_v1 = APIRouter(prefix=API_V1_PREFIX)
    api_v1.include_router(auth_router)
    api_v1.include_router(users.router)
    api_v1.include_router(scripts.router)
    api_v1.include_router(campaigns.router)
    api_v1.include_router(reports.router)
    api_v1.include_router(admin.router)
    api_v1.include_router(webhook.router)
    app.include_router(api_v1)

    _register_protected_docs(app)
    return app


app = create_app()
