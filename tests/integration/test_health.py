"""Smoke-тест health endpoints (NFR-OPS-01)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_returns_200(client) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_returns_200(client) -> None:
    r = await client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}
