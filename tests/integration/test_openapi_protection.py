"""Доступ к /api/docs защищён JWT (FR-API-07)."""

from __future__ import annotations

import pytest

from apps.api.auth.jwt import issue_token_pair
from apps.api.config import get_settings


@pytest.mark.asyncio
async def test_openapi_unauthenticated_returns_401(client) -> None:
    r = await client.get("/api/openapi.json")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["type"].startswith("urn:custdevai:errors:")
    assert "Требуется аутентификация" in body["title"]


@pytest.mark.asyncio
async def test_swagger_ui_unauthenticated_returns_401(client) -> None:
    r = await client.get("/api/docs")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_openapi_authenticated_returns_schema(client, settings) -> None:
    access, _, _, _ = issue_token_pair(user_id=1, roles=["Admin"], settings=get_settings())
    r = await client.get("/api/openapi.json", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    assert "openapi" in r.json()
