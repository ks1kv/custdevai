"""Выдача и валидация JWT-токенов (FR-AUTH-04, NFR-SEC-03).

Access-токен живёт 15 минут, refresh — 7 суток. Каждый токен имеет
уникальный jti (UUID4), позволяющий отзыв через Redis-deny-list.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from apps.api.config import Settings
from apps.api.errors import AuthenticationFailed


class TokenType(str, enum.Enum):
    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True)
class TokenPayload:
    """Распакованное содержимое JWT, удобное для типизированного доступа."""

    sub: int
    jti: str
    type: TokenType
    roles: tuple[str, ...]
    exp: datetime
    iat: datetime


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _build_payload(
    *, user_id: int, token_type: TokenType, ttl: timedelta, roles: list[str]
) -> tuple[dict[str, Any], str]:
    jti = str(uuid.uuid4())
    iat = _utcnow()
    exp = iat + ttl
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "jti": jti,
        "type": token_type.value,
        "roles": roles,
        "iat": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return payload, jti


def issue_token_pair(
    *, user_id: int, roles: list[str], settings: Settings
) -> tuple[str, str, str, str]:
    """Сгенерировать (access, refresh, access_jti, refresh_jti)."""
    access_payload, access_jti = _build_payload(
        user_id=user_id,
        token_type=TokenType.ACCESS,
        ttl=timedelta(minutes=settings.jwt_access_token_ttl_minutes),
        roles=roles,
    )
    refresh_payload, refresh_jti = _build_payload(
        user_id=user_id,
        token_type=TokenType.REFRESH,
        ttl=timedelta(days=settings.jwt_refresh_token_ttl_days),
        roles=roles,
    )
    access = jwt.encode(access_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    refresh = jwt.encode(refresh_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return access, refresh, access_jti, refresh_jti


def decode_token(token: str, *, settings: Settings) -> TokenPayload:
    """Распарсить и провалидировать подпись/срок токена.

    Raises:
        AuthenticationFailed: при просрочке, неверной подписи или
            невалидном содержимом.
    """
    try:
        raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise AuthenticationFailed("Невалидный или просроченный токен.") from exc
    try:
        return TokenPayload(
            sub=int(raw["sub"]),
            jti=str(raw["jti"]),
            type=TokenType(raw["type"]),
            roles=tuple(raw.get("roles", [])),
            exp=datetime.fromtimestamp(int(raw["exp"]), tz=timezone.utc),
            iat=datetime.fromtimestamp(int(raw["iat"]), tz=timezone.utc),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise AuthenticationFailed("Некорректное содержимое токена.") from exc
