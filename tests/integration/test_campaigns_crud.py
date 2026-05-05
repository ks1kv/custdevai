"""CRUD кампаний: соль генерируется, переходы статусов, 409 при удалении сценария."""

from __future__ import annotations

import pytest


async def _login(client, email: str, password: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _create_script(client, headers) -> int:
    r = await client.post(
        "/api/v1/scripts",
        json={"title": "S", "questions": [{"text": "Q?", "order_index": 0}]},
        headers=headers,
    )
    return r.json()["id"]


@pytest.mark.asyncio
async def test_create_campaign_generates_pseudonym_salt(client, seeded_admin) -> None:
    token = await _login(client, seeded_admin["email"], seeded_admin["password"])
    headers = {"Authorization": f"Bearer {token}"}
    sid = await _create_script(client, headers)

    r = await client.post(
        "/api/v1/campaigns",
        json={"title": "Кампания A", "script_id": sid},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["has_pseudonym_salt"] is True


@pytest.mark.asyncio
async def test_delete_script_with_campaign_returns_409(client, seeded_admin) -> None:
    token = await _login(client, seeded_admin["email"], seeded_admin["password"])
    headers = {"Authorization": f"Bearer {token}"}
    sid = await _create_script(client, headers)
    r = await client.post(
        "/api/v1/campaigns",
        json={"title": "C1", "script_id": sid},
        headers=headers,
    )
    assert r.status_code == 200

    r = await client.delete(f"/api/v1/scripts/{sid}", headers=headers)
    assert r.status_code == 409, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert "не может быть удалён" in body["detail"]


@pytest.mark.asyncio
async def test_invalid_status_transition_returns_409(client, seeded_admin) -> None:
    token = await _login(client, seeded_admin["email"], seeded_admin["password"])
    headers = {"Authorization": f"Bearer {token}"}
    sid = await _create_script(client, headers)
    r = await client.post(
        "/api/v1/campaigns",
        json={"title": "C", "script_id": sid},
        headers=headers,
    )
    cid = r.json()["id"]

    # draft → completed: разрешено
    r = await client.patch(
        f"/api/v1/campaigns/{cid}", json={"status": "completed"}, headers=headers
    )
    assert r.status_code == 200

    # completed → running: запрещено (Conflict)
    r = await client.patch(
        f"/api/v1/campaigns/{cid}", json={"status": "running"}, headers=headers
    )
    assert r.status_code == 409
