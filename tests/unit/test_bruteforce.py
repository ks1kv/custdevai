"""Unit-тесты защиты от брутфорса (FR-AUTH-08, NFR-SEC-05)."""

from __future__ import annotations

import pytest

from apps.api.auth.bruteforce import BruteForceGuard, RefreshTokenStore, TokenRevocationStore


@pytest.mark.asyncio
async def test_failed_attempts_count_until_lockout(fake_redis, settings) -> None:
    guard = BruteForceGuard(fake_redis, settings)
    # first 4 → no lockout
    for _ in range(settings.bruteforce_max_attempts - 1):
        assert not await guard.register_failure("1.2.3.4")
    # 5th → lockout
    assert await guard.register_failure("1.2.3.4")
    assert await guard.is_locked("1.2.3.4")


@pytest.mark.asyncio
async def test_reset_clears_lock(fake_redis, settings) -> None:
    guard = BruteForceGuard(fake_redis, settings)
    for _ in range(settings.bruteforce_max_attempts):
        await guard.register_failure("1.2.3.4")
    assert await guard.is_locked("1.2.3.4")
    await guard.reset("1.2.3.4")
    assert not await guard.is_locked("1.2.3.4")


@pytest.mark.asyncio
async def test_revocation_store_marks_jti(fake_redis) -> None:
    store = TokenRevocationStore(fake_redis)
    await store.revoke("abc", ttl_seconds=60)
    assert await store.is_revoked("abc")
    assert not await store.is_revoked("xyz")


@pytest.mark.asyncio
async def test_revocation_store_skips_zero_ttl(fake_redis) -> None:
    store = TokenRevocationStore(fake_redis)
    await store.revoke("abc", ttl_seconds=0)
    assert not await store.is_revoked("abc")


@pytest.mark.asyncio
async def test_refresh_store_consume_returns_existence(fake_redis) -> None:
    store = RefreshTokenStore(fake_redis)
    await store.remember("rj", 1, ttl_seconds=60)
    assert await store.consume("rj")
    # повторный consume — уже нет
    assert not await store.consume("rj")
