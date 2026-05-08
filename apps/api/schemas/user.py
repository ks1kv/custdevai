"""DTO для административного управления пользователями."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_EMAIL = r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"


class UserCreate(BaseModel):
    email: str = Field(pattern=_EMAIL, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=256)
    role_names: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class UserRolesAssign(BaseModel):
    role_names: list[str] = Field(min_length=1)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str | None
    is_active: bool
    must_change_password: bool
    researcher_telegram_chat_id: int | None = None
    roles: list[str] = Field(default_factory=list)


class MyProfileUpdate(BaseModel):
    """Self-update полей собственного профиля (FR-BOT-09 закрытие)."""

    full_name: str | None = Field(default=None, max_length=255)
    researcher_telegram_chat_id: int | None = None


class PasswordResetResponse(BaseModel):
    user_id: int
    email: str
    temporary_password: str
    must_change_password: bool = True
