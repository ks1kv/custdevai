"""Pydantic-схемы аутентификации (FR-AUTH-04)."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Достаточный регекс для валидации формата email на уровне DTO.
# Полная RFC 5322 проверка не нужна — пользователи создаются админом
# вручную, а не через публичную регистрацию.
_EMAIL_PATTERN = r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"


class LoginRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    must_change_password: bool = False
    # TTL access-токена в секундах. Нужен SPA для проактивного refresh
    # (запускается за минуту до истечения, FR-AUTH-04).
    expires_in: int = 0
