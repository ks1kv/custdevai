"""FastAPI-зависимости: текущий пользователь, проверка ролей, доступ к Redis/БД."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.bruteforce import (
    BruteForceGuard,
    RefreshTokenStore,
    TokenRevocationStore,
)
from apps.api.auth.jwt import TokenPayload, TokenType, decode_token
from apps.api.auth.rbac import Role, require
from apps.api.auth.redis_client import get_redis
from apps.api.config import Settings, get_settings
from apps.api.db.session import get_db
from apps.api.errors import AuthenticationFailed


@dataclass(frozen=True)
class CurrentUser:
    id: int
    roles: tuple[str, ...]
    jti: str
    exp_seconds: int


def get_settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_redis_dep() -> AsyncIterator[Redis]:
    yield get_redis()


RedisDep = Annotated[Redis, Depends(get_redis_dep)]


def get_revocation_store(redis: RedisDep) -> TokenRevocationStore:
    return TokenRevocationStore(redis)


def get_refresh_store(redis: RedisDep) -> RefreshTokenStore:
    return RefreshTokenStore(redis)


def get_brute_force_guard(redis: RedisDep, settings: SettingsDep) -> BruteForceGuard:
    return BruteForceGuard(redis, settings)


RevocationDep = Annotated[TokenRevocationStore, Depends(get_revocation_store)]
RefreshStoreDep = Annotated[RefreshTokenStore, Depends(get_refresh_store)]
BruteForceDep = Annotated[BruteForceGuard, Depends(get_brute_force_guard)]


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Возвращает токен из 'Bearer <token>' или None если заголовок пуст/не bearer."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(None, 1)[1]


async def get_current_user(
    settings: SettingsDep,
    revoked: RevocationDep,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    access_cookie: Annotated[str | None, Cookie(alias="access_token")] = None,
) -> CurrentUser:
    """Декодировать access-токен из заголовка Authorization или cookie (SPA)."""
    token = _extract_bearer_token(authorization) or access_cookie
    if not token:
        raise AuthenticationFailed("Требуется access-токен (заголовок Authorization или cookie).")
    payload: TokenPayload = decode_token(token, settings=settings)
    if payload.type is not TokenType.ACCESS:
        raise AuthenticationFailed("Ожидался access-токен.")
    if await revoked.is_revoked(payload.jti):
        raise AuthenticationFailed("Токен отозван.")
    exp_seconds = max(0, int((payload.exp - payload.iat).total_seconds()))
    return CurrentUser(
        id=payload.sub,
        roles=payload.roles,
        jti=payload.jti,
        exp_seconds=exp_seconds,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[CurrentUser], CurrentUser]:
    """Фабрика зависимости: вернуть пользователя, если у него есть хотя бы одна из ролей."""

    async def _checker(user: CurrentUserDep) -> CurrentUser:
        require(roles, user.roles)
        return user

    return _checker


def get_client_ip(request: Request) -> str:
    """Достать IP клиента, учитывая X-Forwarded-For за обратным прокси."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "0.0.0.0"
