"""Unit-тесты универсальной пагинации (NFR-PRF-03)."""

from __future__ import annotations

import pytest

from apps.api.errors import ValidationFailed
from apps.api.schemas.pagination import Page, PaginationParams


def test_default_limit_matches_settings(settings) -> None:
    params = PaginationParams()
    assert params.limit == settings.default_page_size
    assert params.offset == 0


def test_validated_rejects_oversize(settings) -> None:
    params = PaginationParams(limit=settings.max_page_size + 1)
    with pytest.raises(ValidationFailed):
        params.validated()


def test_page_serialization_round_trip() -> None:
    page: Page[int] = Page[int](items=[1, 2, 3], total=10, limit=3, offset=0)
    assert page.model_dump()["total"] == 10
