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
