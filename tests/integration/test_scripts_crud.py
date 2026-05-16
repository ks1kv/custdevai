"""CRUD сценариев: 200/404/403/409 (FR-API-01, FR-AUTH-05)."""

from __future__ import annotations

import pytest


async def _login(client, email: str, password: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_admin_can_create_list_get_delete_script(client, seeded_admin) -> None:
    token = await _login(client, seeded_admin["email"], seeded_admin["password"])
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/v1/scripts",
        json={
            "title": "Опрос S1",
            "description": "Тестовый сценарий",
            "questions": [
                {"text": "Какой ваш пол?", "order_index": 0, "is_required": True},
                {"text": "Ваш возраст?", "order_index": 1, "is_required": True},
            ],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    script = r.json()
    assert script["title"] == "Опрос S1"
    assert len(script["questions"]) == 2
    sid = script["id"]

    # list
    r = await client.get("/api/v1/scripts", headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # get
    r = await client.get(f"/api/v1/scripts/{sid}", headers=headers)
    assert r.status_code == 200

    # patch
    r = await client.patch(f"/api/v1/scripts/{sid}", json={"title": "Опрос S1.1"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["title"] == "Опрос S1.1"

    # delete
    r = await client.delete(f"/api/v1/scripts/{sid}", headers=headers)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_get_unknown_script_returns_404_problem_details(client, seeded_admin) -> None:
    token = await _login(client, seeded_admin["email"], seeded_admin["password"])
    r = await client.get("/api/v1/scripts/9999", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_patch_script_replaces_questions(client, seeded_admin) -> None:
    """PATCH /scripts/{id} с полем questions полностью заменяет набор."""
    token = await _login(client, seeded_admin["email"], seeded_admin["password"])
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/v1/scripts",
        json={
            "title": "S",
            "questions": [
                {"text": "Q1", "order_index": 1, "is_required": True},
                {"text": "Q2", "order_index": 2, "is_required": True},
            ],
        },
        headers=headers,
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    r = await client.patch(
        f"/api/v1/scripts/{sid}",
        json={
            "questions": [
                {"text": "Q1-edited", "order_index": 1, "is_required": True},
                {"text": "Q2-edited", "order_index": 2, "is_required": False},
                {"text": "Q3-new", "order_index": 3, "is_required": True},
            ],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [q["text"] for q in body["questions"]] == ["Q1-edited", "Q2-edited", "Q3-new"]
    assert body["questions"][1]["is_required"] is False
