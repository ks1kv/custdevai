"""Фикстуры интеграционных тестов: FastAPI TestClient с подменой БД и Redis."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.config import get_settings
from apps.api.db.base import Base
from apps.api.db.session import get_db
from apps.api.deps import get_redis_dep
from apps.api.main import create_app

# SQLite в памяти достаточно для smoke-проверок CRUD на уровне ORM
# (без проверки PostgreSQL-специфичных типов вроде ENUM/INET/JSONB —
# для них есть отдельный test_migrations с пометкой integration).
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _patch_bigint_for_sqlite() -> None:
    """SQLite autoincrement-ит только INTEGER PRIMARY KEY, не BIGINT.

    Подменяем компиляцию BIGINT в "INTEGER" для sqlite, чтобы Base.metadata
    с BigInteger PK прошёл create_all. На Postgres продолжает использоваться
    BIGINT — это не задевает основную схему.
    """
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_to_integer(element, compiler, **kw):  # type: ignore[no-untyped-def]
        return "INTEGER"


_patch_bigint_for_sqlite()


@pytest_asyncio.fixture
async def test_engine():
    pytest.importorskip("aiosqlite")
    engine = create_async_engine(TEST_DATABASE_URL, future=True)

    # SQLite не знает функцию char_length() (Postgres-only). Регистрируем
    # её на каждое подключение как алиас len() — нужно для CHECK-constraint
    # answers_text_length (FR-API-08 + FR-BOT-08 валидация длины).
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _register_char_length(dbapi_connection, _record):
        dbapi_connection.create_function("char_length", 1, lambda s: len(s) if s else 0)

    # Создаём только подмножество таблиц, не зависящих от Postgres-only типов.
    # Полная схема проверяется отдельно интеграционным test_migrations.
    from apps.api.db.models import (  # noqa: F401  (нужно для регистрации в metadata)
        AuditLog,
        Campaign,
        Consent,
        InterviewSession,
        Question,
        Role,
        Script,
        SentimentResult,
        SessionTopic,
        Topic,
        User,
        UserRole,
    )

    async with engine.begin() as conn:
        # На Phase 3 sentiment_results включён в схему. topics + session_topics
        # используют PG-only ARRAY(Text), на SQLite не поддерживается;
        # пропускаем — Phase 3 ML-тесты используют FakeModeler без INSERT
        # в topics (orchestration уровень).
        skip = {
            "topics",
            "session_topics",
        }
        meta = Base.metadata
        await conn.run_sync(
            lambda c: meta.create_all(
                bind=c, tables=[t for t in meta.sorted_tables if t.name not in skip]
            )
        )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    sessionmaker = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)
    async with sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
async def app(test_engine, fake_redis):
    """FastAPI app с подменёнными зависимостями get_db и get_redis_dep."""
    sessionmaker = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)

    get_settings.cache_clear()
    application = create_app()

    async def _override_db() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as s:
            try:
                yield s
            except Exception:
                await s.rollback()
                raise

    async def _override_redis() -> AsyncIterator[Any]:
        yield fake_redis

    application.dependency_overrides[get_db] = _override_db
    application.dependency_overrides[get_redis_dep] = _override_redis
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def seeded_admin(db_session) -> dict[str, int | str]:
    """Создать роли и одного admin-пользователя в тестовой БД."""
    from apps.api.auth.passwords import hash_password
    from apps.api.db.models import Role, User, UserRole

    roles = {
        "Admin": Role(id=1, name="Admin"),
        "Researcher": Role(id=2, name="Researcher"),
        "Analyst": Role(id=3, name="Analyst"),
        "Respondent": Role(id=4, name="Respondent"),
    }
    for r in roles.values():
        db_session.add(r)
    await db_session.flush()

    user = User(
        email="admin@example.com",
        full_name="Admin",
        password_hash=hash_password("Test12345!", cost=12),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=roles["Admin"].id))
    await db_session.commit()
    return {"id": user.id, "email": user.email, "password": "Test12345!"}
