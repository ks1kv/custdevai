"""Универсальная пагинация (NFR-PRF-03)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

from apps.api.config import get_settings
from apps.api.errors import ValidationFailed

T = TypeVar("T")


@dataclass
class PaginationParams:
    """Lightweight DTO для query-параметров limit/offset."""

    limit: int
    offset: int

    def validated(self) -> "PaginationParams":
        max_size = get_settings().max_page_size
        if self.limit > max_size:
            raise ValidationFailed(
                f"Размер страницы превышает максимум {max_size}.",
                errors=[
                    {
                        "loc": ["query", "limit"],
                        "msg": f"limit ≤ {max_size}",
                        "type": "value_error",
                    }
                ],
            )
        return self


def pagination_dependency(
    limit: int = Query(default=0, ge=0),
    offset: int = Query(default=0, ge=0),
) -> PaginationParams:
    """FastAPI Depends-провайдер пагинации с дефолтом из Settings."""
    if limit == 0:
        limit = get_settings().default_page_size
    return PaginationParams(limit=limit, offset=offset)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
