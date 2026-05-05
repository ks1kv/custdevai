"""Unit-тесты RFC 7807 ошибок (FR-API-02)."""

from __future__ import annotations

from apps.api.errors import (
    ERROR_NS,
    APIError,
    AuthenticationFailed,
    Conflict,
    NotFound,
    PermissionDenied,
    RateLimited,
    ValidationFailed,
)
from apps.api.schemas.problem import PROBLEM_CONTENT_TYPE


def test_problem_content_type() -> None:
    assert PROBLEM_CONTENT_TYPE == "application/problem+json"


def test_validation_failed_problem_payload() -> None:
    err = ValidationFailed(
        "Поле email отсутствует.", errors=[{"loc": ["body"], "msg": "x", "type": "y"}]
    )
    p = err.to_problem(instance="https://example/api")
    dump = p.model_dump(exclude_none=True)
    assert dump["status"] == 400
    assert dump["type"] == f"{ERROR_NS}validation"
    assert dump["title"] == "Ошибка валидации входных данных"
    assert dump["detail"].startswith("Поле email")
    assert dump["instance"].startswith("https://")
    assert dump["errors"][0]["loc"] == ["body"]


def test_each_error_has_unique_type_suffix() -> None:
    suffixes = {
        cls.type_suffix
        for cls in (
            APIError,
            ValidationFailed,
            AuthenticationFailed,
            PermissionDenied,
            NotFound,
            Conflict,
            RateLimited,
        )
    }
    assert len(suffixes) == 7


def test_titles_are_in_russian() -> None:
    for cls in (
        ValidationFailed,
        AuthenticationFailed,
        PermissionDenied,
        NotFound,
        Conflict,
        RateLimited,
    ):
        # все заголовки содержат кириллические символы
        assert any("Ѐ" <= ch <= "ӿ" for ch in cls.title)
