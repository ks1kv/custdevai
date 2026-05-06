"""Unit-тесты Settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.config import Settings


def test_bcrypt_below_minimum_fails() -> None:
    with pytest.raises(ValidationError):
        Settings(  # type: ignore[call-arg]
            postgres_password="x",
            jwt_secret="a" * 32,
            pseudonym_master_salt="b" * 32,
            bcrypt_cost_factor=11,
        )


def test_short_jwt_secret_fails() -> None:
    with pytest.raises(ValidationError):
        Settings(  # type: ignore[call-arg]
            postgres_password="x",
            jwt_secret="short",
            pseudonym_master_salt="b" * 32,
        )


def test_effective_database_url_composes_from_parts(settings) -> None:
    assert "postgresql+asyncpg" in settings.effective_database_url
