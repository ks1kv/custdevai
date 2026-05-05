"""Unit-тесты JWT-утилит (FR-AUTH-04, NFR-SEC-03)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

from apps.api.auth.jwt import TokenType, decode_token, issue_token_pair
from apps.api.errors import AuthenticationFailed


def test_issue_token_pair_returns_valid_tokens(settings) -> None:
    access, refresh, access_jti, refresh_jti = issue_token_pair(
        user_id=42, roles=["Admin"], settings=settings
    )
    assert access and refresh
    assert access_jti != refresh_jti

    a = decode_token(access, settings=settings)
    r = decode_token(refresh, settings=settings)
    assert a.sub == 42 and r.sub == 42
    assert a.type is TokenType.ACCESS
    assert r.type is TokenType.REFRESH
    assert "Admin" in a.roles


def test_access_token_expires_after_15_minutes(settings) -> None:
    with freeze_time("2026-05-05 10:00:00"):
        access, _, _, _ = issue_token_pair(
            user_id=1, roles=[], settings=settings
        )
    with freeze_time("2026-05-05 10:16:00"):
        with pytest.raises(AuthenticationFailed):
            decode_token(access, settings=settings)


def test_refresh_token_lifetime_seven_days(settings) -> None:
    with freeze_time("2026-05-05 10:00:00"):
        _, refresh, _, _ = issue_token_pair(
            user_id=1, roles=[], settings=settings
        )
        payload = decode_token(refresh, settings=settings)
    assert (payload.exp - payload.iat) == timedelta(days=7)


def test_decode_rejects_garbage_token(settings) -> None:
    with pytest.raises(AuthenticationFailed):
        decode_token("not.a.token", settings=settings)


def test_decode_rejects_token_signed_by_other_secret(settings) -> None:
    from copy import copy

    other = copy(settings)
    other.jwt_secret = "x" * 32
    access, _, _, _ = issue_token_pair(user_id=1, roles=[], settings=other)
    with pytest.raises(AuthenticationFailed):
        decode_token(access, settings=settings)
