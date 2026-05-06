"""HTTP middleware: HTTPSRedirect и базовое логирование запросов."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from apps.api.config import Settings
from apps.api.schemas.problem import PROBLEM_CONTENT_TYPE, ProblemDetail

logger = logging.getLogger(__name__)


class RequireHTTPSMiddleware(BaseHTTPMiddleware):
    """Отказывает HTTP-запросам в production (NFR-SEC-01).

    Не делает редирект на https — за reverse-proxy редирект уже происходит
    на уровне TLS-терминатора (nginx / ingress). Здесь же при попытке
    дойти до приложения по plain HTTP мы возвращаем 400 Problem-Details.
    """

    def __init__(self, app: FastAPI, *, enabled: bool) -> None:
        super().__init__(app)
        self._enabled = enabled

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if self._enabled:
            scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
            if scheme.lower() != "https":
                problem = ProblemDetail(
                    type="urn:custdevai:errors:insecure-transport",
                    title="HTTPS обязателен",
                    status=400,
                    detail="HTTP-соединения в production отключены. Используйте HTTPS (TLS 1.2+).",
                    instance=str(request.url),
                )
                return JSONResponse(
                    status_code=400,
                    content=problem.model_dump(exclude_none=True),
                    media_type=PROBLEM_CONTENT_TYPE,
                )
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Простое access-логирование с временем обработки."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        logger.info(
            "%s %s -> %d (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


def register_middleware(app: FastAPI, settings: Settings) -> None:
    if settings.is_production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*"],  # реальный whitelist хостов задаётся за прокси
        )
    app.add_middleware(RequireHTTPSMiddleware, enabled=settings.is_production)
    app.add_middleware(RequestLoggingMiddleware)
