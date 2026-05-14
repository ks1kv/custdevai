"""Unit-тесты deep-link парсера (FR-BOT-01)."""

from __future__ import annotations

import pytest

from apps.bot.deeplink import InvalidDeepLink, build_payload, parse_campaign_id


def test_parse_simple() -> None:
    assert parse_campaign_id("c123") == 123


def test_parse_with_whitespace() -> None:
    assert parse_campaign_id(" c42 ") == 42


@pytest.mark.parametrize("payload", ["", None, "abc", "c", "1", "c-1", "c1.2", "C100"])
def test_parse_rejects_garbage(payload) -> None:
    with pytest.raises(InvalidDeepLink):
        parse_campaign_id(payload)


def test_build_payload_round_trip() -> None:
    assert parse_campaign_id(build_payload(99)) == 99


def test_build_payload_rejects_zero_or_negative() -> None:
    with pytest.raises(ValueError):
        build_payload(0)
    with pytest.raises(ValueError):
        build_payload(-1)


# ----- Phase 5: HMAC-подписанные deep-links -------------------------------


_MASTER_SALT = "a" * 64  # 32 hex bytes


def test_signed_payload_round_trip() -> None:
    payload = build_payload(123, master_salt=_MASTER_SALT)
    assert "." in payload  # signed format c<id>.<sig>
    assert parse_campaign_id(payload, master_salt=_MASTER_SALT) == 123


def test_signed_payload_rejects_tampered_signature() -> None:
    payload = build_payload(123, master_salt=_MASTER_SALT)
    # Заменяем одну букву в подписи на любой другой base32-символ.
    base = payload[:-1]
    last_char = payload[-1]
    replacement = "X" if last_char != "X" else "Y"
    tampered = base + replacement
    with pytest.raises(InvalidDeepLink):
        parse_campaign_id(tampered, master_salt=_MASTER_SALT)


def test_signed_payload_rejects_wrong_secret() -> None:
    payload = build_payload(123, master_salt=_MASTER_SALT)
    with pytest.raises(InvalidDeepLink):
        parse_campaign_id(payload, master_salt="b" * 64)


def test_signed_payload_requires_secret_to_verify() -> None:
    payload = build_payload(7, master_salt=_MASTER_SALT)
    with pytest.raises(InvalidDeepLink):
        parse_campaign_id(payload, master_salt=None)


def test_legacy_unsigned_still_accepted() -> None:
    # Старые ссылки `c<id>` продолжают работать (deprecation period).
    assert parse_campaign_id("c42", master_salt=_MASTER_SALT) == 42


def test_signed_payload_different_for_different_ids() -> None:
    a = build_payload(1, master_salt=_MASTER_SALT)
    b = build_payload(2, master_salt=_MASTER_SALT)
    assert a != b
    # Подпись id=1 не валидна для id=2.
    sig_of_1 = a.split(".")[1]
    forged = f"c2.{sig_of_1}"
    with pytest.raises(InvalidDeepLink):
        parse_campaign_id(forged, master_salt=_MASTER_SALT)
