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


def test_topic_min_corpus_size_default_and_bounds() -> None:
    """Защита от регрессии: дефолт topic_min_corpus_size должен покрывать
    минимум для работы UMAP/HDBSCAN. См. apps/worker/tasks/ml_pipeline.py
    — на корпусе меньше этого порога BERTopic не запускается, иначе UMAP
    падает с «k >= N»."""
    s = Settings(  # type: ignore[call-arg]
        postgres_password="x",
        jwt_secret="a" * 32,
        pseudonym_master_salt="b" * 32,
    )
    assert s.topic_min_corpus_size == 10
    # bounds validation
    with pytest.raises(ValidationError):
        Settings(  # type: ignore[call-arg]
            postgres_password="x",
            jwt_secret="a" * 32,
            pseudonym_master_salt="b" * 32,
            topic_min_corpus_size=1,
        )
