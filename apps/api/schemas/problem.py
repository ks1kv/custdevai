"""Модель ProblemDetail по RFC 7807 (FR-API-02).

Все ошибки API возвращаются в формате application/problem+json с
человекочитаемыми сообщениями на русском языке.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProblemDetail(BaseModel):
    """Тело ответа об ошибке по стандарту RFC 7807."""

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(default="about:blank", description="URI-идентификатор типа ошибки")
    title: str = Field(description="Краткий заголовок ошибки на русском языке")
    status: int = Field(description="HTTP-статус ответа")
    detail: str | None = Field(default=None, description="Подробное описание на русском")
    instance: str | None = Field(default=None, description="URI конкретного запроса")
    errors: list[dict[str, Any]] | None = Field(
        default=None,
        description="Детали по полям при ошибках валидации (loc, msg, type)",
    )


PROBLEM_CONTENT_TYPE = "application/problem+json"
