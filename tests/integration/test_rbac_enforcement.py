"""RBAC: 403 для не-admin на /users (FR-AUTH-05)."""

from __future__ import annotations

import pytest

from apps.api.auth.passwords import hash_password


@pytest.mark.asyncio
async def test_researcher_cannot_create_user(client, db_session) -> None:
    from apps.api.db.models import Role, User, UserRole

    for r in [
        Role(id=1, name="Admin"),
        Role(id=2, name="Researcher"),
        Role(id=3, name="Analyst"),
        Role(id=4, name="Respondent"),
    ]:
        db_session.add(r)
    await db_session.flush()
    u = User(
        email="r@x.com",
        password_hash=hash_password("Test12345!", cost=12),
    )
    db_session.add(u)
    await db_session.flush()
    db_session.add(UserRole(user_id=u.id, role_id=2))  # Researcher
    await db_session.commit()

    r = await client.post("/api/v1/auth/login", json={"email": "r@x.com", "password": "Test12345!"})
    token = r.json()["access_token"]

    r = await client.post(
        "/api/v1/users",
        json={"email": "n@x.com", "password": "Test12345!", "role_names": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    body = r.json()
    assert "запрещ" in body["title"].lower() or "forbidden" in body["title"].lower()
