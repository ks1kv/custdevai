"""Полный auth flow (login → refresh → logout) с подменой БД и Redis."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(client, seeded_admin) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded_admin["email"], "password": "wrong"},
    )
    assert r.status_code == 401
    assert "title" in r.json()


@pytest.mark.asyncio
async def test_login_then_use_access_token(client, seeded_admin) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded_admin["email"], "password": seeded_admin["password"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]

    # Используем access — должен пройти на /api/v1/scripts
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    r2 = await client.get("/api/v1/scripts", headers=headers)
    assert r2.status_code == 200
    page = r2.json()
    assert page["items"] == [] and page["total"] == 0


@pytest.mark.asyncio
async def test_refresh_rotates_tokens(client, seeded_admin) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded_admin["email"], "password": seeded_admin["password"]},
    )
    refresh1 = r.json()["refresh_token"]
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
    assert r2.status_code == 200, r2.text
    refresh2 = r2.json()["refresh_token"]
    assert refresh2 != refresh1
    # Старый refresh уже не работает (consume вернёт false → 401)
    r3 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
    assert r3.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_access(client, seeded_admin) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded_admin["email"], "password": seeded_admin["password"]},
    )
    body = r.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    r2 = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": body["refresh_token"]},
        headers=headers,
    )
    assert r2.status_code == 200
    # После logout access-токен попадает в deny-list
    r3 = await client.get("/api/v1/scripts", headers=headers)
    assert r3.status_code == 401


@pytest.mark.asyncio
async def test_lockout_after_5_failed_attempts(client, seeded_admin) -> None:
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"email": seeded_admin["email"], "password": "wrong"},
        )
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded_admin["email"], "password": seeded_admin["password"]},
    )
    assert r.status_code == 429
    assert r.headers["content-type"].startswith("application/problem+json")
    # RFC 6585 §4: 429 ответ выставляет Retry-After в секундах (NFR-SEC-05).
    assert "retry-after" in {k.lower() for k in r.headers}
    assert int(r.headers["retry-after"]) > 0
