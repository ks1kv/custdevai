"""Универсальная пагинация (NFR-PRF-03)."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from apps.api.config import get_settings
from apps.api.errors import ValidationFailed

T = TypeVar("T")


class PaginationParams(BaseModel):
    limit: int = Field(default_factory=lambda: get_settings().default_page_size, ge=1)
    offset: int = Field(default=0, ge=0)

    def validated(self) -> "PaginationParams":
        max_size = get_settings().max_page_size
        if self.limit > max_size:
            raise ValidationFailed(
                f"Размер страницы превышает максимум {max_size}.",
                errors=[{"loc": ["query", "limit"], "msg": f"limit ≤ {max_size}", "type": "value_error"}],
            )
        return self


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
