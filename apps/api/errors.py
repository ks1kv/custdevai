"""Иерархия доменных исключений и их преобразование в RFC 7807 (FR-API-02).

Все исключения, наследующие `APIError`, автоматически конвертируются
exception-handler-ом в ответ `application/problem+json` с русским
сообщением. Любое непойманное исключение → 500 с обобщённым detail
(стектрейс не попадает в тело — NFR-SEC-07).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.schemas.problem import PROBLEM_CONTENT_TYPE, ProblemDetail

logger = logging.getLogger(__name__)

ERROR_NS = "urn:custdevai:errors:"


class APIError(Exception):
    """Базовый класс для всех ожидаемых ошибок API.

    Attributes:
        status_code: HTTP-статус ответа.
        title: Короткий заголовок на русском.
        detail: Развёрнутое описание на русском.
        type_suffix: Идентификатор внутри пространства urn:custdevai:errors.
        errors: Опциональные подробности по полям (валидация).
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    title: str = "Внутренняя ошибка"
    type_suffix: str = "internal"

    def __init__(
        self,
        detail: str | None = None,
        *,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.detail = detail
        self.errors = errors
        super().__init__(detail or self.title)

    def to_problem(self, instance: str | None = None) -> ProblemDetail:
        return ProblemDetail(
            type=f"{ERROR_NS}{self.type_suffix}",
            title=self.title,
            status=self.status_code,
            detail=self.detail,
            instance=instance,
            errors=self.errors,
        )


class ValidationFailed(APIError):
    status_code = status.HTTP_400_BAD_REQUEST
    title = "Ошибка валидации входных данных"
    type_suffix = "validation"


class AuthenticationFailed(APIError):
    status_code = status.HTTP_401_UNAUTHORIZED
    title = "Требуется аутентификация"
    type_suffix = "authentication"


class PermissionDenied(APIError):
    status_code = status.HTTP_403_FORBIDDEN
    title = "Доступ запрещён"
    type_suffix = "forbidden"


class NotFound(APIError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Ресурс не найден"
    type_suffix = "not-found"


class Conflict(APIError):
    status_code = status.HTTP_409_CONFLICT
    title = "Конфликт состояния"
    type_suffix = "conflict"


class RateLimited(APIError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    title = "Слишком много запросов"
    type_suffix = "rate-limit"


def _problem_response(problem: ProblemDetail) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_CONTENT_TYPE,
    )


async def _api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return _problem_response(exc.to_problem(instance=str(request.url)))


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    title_map = {
        400: "Некорректный запрос",
        401: "Требуется аутентификация",
        403: "Доступ запрещён",
        404: "Ресурс не найден",
        405: "Метод не поддерживается",
        409: "Конфликт состояния",
        415: "Неподдерживаемый тип содержимого",
        422: "Ошибка валидации входных данных",
        429: "Слишком много запросов",
    }
    detail = exc.detail if isinstance(exc.detail, str) else None
    problem = ProblemDetail(
        type=f"{ERROR_NS}http",
        title=title_map.get(exc.status_code, "Ошибка HTTP"),
        status=exc.status_code,
        detail=detail,
        instance=str(request.url),
    )
    return _problem_response(problem)


async def _validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {"loc": list(err.get("loc", [])), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    problem = ProblemDetail(
        type=f"{ERROR_NS}validation",
        title="Ошибка валидации входных данных",
        status=status.HTTP_400_BAD_REQUEST,
        detail="Тело запроса не прошло проверку схемы.",
        instance=str(request.url),
        errors=errors,
    )
    return _problem_response(problem)


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s", request.url, exc_info=exc)
    problem = ProblemDetail(
        type=f"{ERROR_NS}internal",
        title="Внутренняя ошибка",
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Произошла непредвиденная ошибка. Попробуйте повторить запрос позже.",
        instance=str(request.url),
    )
    return _problem_response(problem)


def register_error_handlers(app: FastAPI) -> None:
    """Подключить все exception-handlers к приложению."""
    app.add_exception_handler(APIError, _api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_handler)
