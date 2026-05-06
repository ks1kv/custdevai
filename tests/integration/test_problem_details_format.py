"""Формат RFC 7807 на реальных запросах (FR-API-02)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_problem_details(client) -> None:
    r = await client.get("/api/v1/scripts")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 401
    assert "title" in body and any("Ѐ" <= c <= "ӿ" for c in body["title"])


@pytest.mark.asyncio
async def test_validation_error_returns_problem_details(client) -> None:
    # пустое тело логина → 400 (ValidationError → ValidationFailed handler)
    r = await client.post("/api/v1/auth/login", json={})
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["type"].endswith("validation")
    assert isinstance(body.get("errors"), list)
