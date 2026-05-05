"""Unit-тесты bcrypt-хеширования (FR-AUTH-03, NFR-SEC-02)."""

from __future__ import annotations

import pytest

from apps.api.auth.passwords import (
    MIN_COST,
    generate_temporary_password,
    hash_password,
    verify_password,
)


def test_hash_and_verify_round_trip() -> None:
    h = hash_password("Test12345!", cost=MIN_COST)
    assert verify_password("Test12345!", h)
    assert not verify_password("wrong", h)


def test_cost_factor_below_minimum_raises() -> None:
    with pytest.raises(ValueError, match="bcrypt cost factor"):
        hash_password("any", cost=MIN_COST - 1)


def test_hash_format_indicates_cost_at_least_12() -> None:
    h = hash_password("any", cost=MIN_COST)
    # bcrypt-хеш формата $2b$12$...
    parts = h.split("$")
    assert parts[1] in {"2a", "2b", "2y"}
    assert int(parts[2]) >= MIN_COST


def test_temporary_password_meets_length() -> None:
    p1 = generate_temporary_password()
    p2 = generate_temporary_password()
    assert len(p1) == 16
    assert p1 != p2  # практически невозможно совпасть из CSPRNG


def test_verify_returns_false_on_garbage_hash() -> None:
    assert not verify_password("anything", "not-a-bcrypt-hash")
