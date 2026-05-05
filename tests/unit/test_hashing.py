"""Unit-тесты SHA-256 хеширования telegram_id (FR-DB-03, NFR-SEC-08)."""

from __future__ import annotations

import pytest

from apps.api.auth.hashing import derive_campaign_salt, hash_telegram_id, random_campaign_salt


def test_derive_campaign_salt_is_32_bytes() -> None:
    salt = derive_campaign_salt(master_salt_hex="ab" * 32, campaign_id=1)
    assert len(salt) == 32


def test_derive_campaign_salt_is_deterministic() -> None:
    s1 = derive_campaign_salt(master_salt_hex="ab" * 32, campaign_id=42)
    s2 = derive_campaign_salt(master_salt_hex="ab" * 32, campaign_id=42)
    assert s1 == s2


def test_derive_campaign_salt_differs_per_campaign() -> None:
    s1 = derive_campaign_salt(master_salt_hex="ab" * 32, campaign_id=1)
    s2 = derive_campaign_salt(master_salt_hex="ab" * 32, campaign_id=2)
    assert s1 != s2


def test_short_master_salt_rejected() -> None:
    with pytest.raises(ValueError):
        derive_campaign_salt(master_salt_hex="ab", campaign_id=1)


def test_random_salt_unique() -> None:
    assert random_campaign_salt() != random_campaign_salt()


def test_hash_telegram_id_length_and_determinism() -> None:
    salt = bytes(32)
    h1 = hash_telegram_id(123, salt)
    h2 = hash_telegram_id(123, salt)
    assert len(h1) == 32
    assert h1 == h2


def test_hash_telegram_id_changes_with_salt() -> None:
    h1 = hash_telegram_id(123, bytes(32))
    h2 = hash_telegram_id(123, bytes([1] + [0] * 31))
    assert h1 != h2


def test_hash_telegram_id_rejects_wrong_salt_length() -> None:
    with pytest.raises(ValueError):
        hash_telegram_id(123, bytes(16))
