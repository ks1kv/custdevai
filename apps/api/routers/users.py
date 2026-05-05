"""Admin-only управление пользователями (FR-AUTH-01, 02, 06)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from apps.api.auth.email import EmailNotifier, LoggingEmailNotifier
from apps.api.auth.rbac import Role
from apps.api.db.models import User
from apps.api.deps import CurrentUser, DBSession, SettingsDep, get_client_ip, require_roles
from apps.api.schemas.user import (
    PasswordResetResponse,
    UserCreate,
    UserOut,
    UserRolesAssign,
    UserUpdate,
)
from apps.api.services.users import UserService

router = APIRouter(prefix="/users", tags=["users"])

_admin_only = require_roles(Role.ADMIN)


def get_email_notifier() -> EmailNotifier:
    """Phase 1: всегда LoggingEmailNotifier; в Phase 5 будет SMTP-реализация."""
    return LoggingEmailNotifier()


def _service(
    session: DBSession,
    settings: SettingsDep,
    email_notifier: EmailNotifier = Depends(get_email_notifier),
) -> UserService:
    return UserService(session=session, settings=settings, email_notifier=email_notifier)


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        roles=[r.name for r in (user.roles or [])],
    )


@router.post("", response_model=UserOut, summary="Создать пользователя")
async def create_user(
    payload: UserCreate,
    request: Request,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_admin_only),
    email_notifier: EmailNotifier = Depends(get_email_notifier),
) -> UserOut:
    service = _service(session, settings, email_notifier)
    user = await service.create(
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
        role_names=payload.role_names,
        actor_id=actor.id,
        ip=get_client_ip(request),
    )
    return _to_out(user)


@router.patch("/{user_id}", response_model=UserOut, summary="Обновить пользователя")
async def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_admin_only),
    email_notifier: EmailNotifier = Depends(get_email_notifier),
) -> UserOut:
    service = _service(session, settings, email_notifier)
    user = await service.update(
        user_id=user_id,
        full_name=payload.full_name,
        is_active=payload.is_active,
        actor_id=actor.id,
        ip=get_client_ip(request),
    )
    await session.refresh(user, attribute_names=["roles"])
    return _to_out(user)


@router.post("/{user_id}/deactivate", response_model=UserOut, summary="Деактивировать пользователя")
async def deactivate_user(
    user_id: int,
    request: Request,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_admin_only),
    email_notifier: EmailNotifier = Depends(get_email_notifier),
) -> UserOut:
    service = _service(session, settings, email_notifier)
    user = await service.deactivate(user_id=user_id, actor_id=actor.id, ip=get_client_ip(request))
    await session.refresh(user, attribute_names=["roles"])
    return _to_out(user)


@router.post(
    "/{user_id}/reset-password",
    response_model=PasswordResetResponse,
    summary="Сбросить пароль (FR-AUTH-06)",
)
async def reset_password(
    user_id: int,
    request: Request,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_admin_only),
    email_notifier: EmailNotifier = Depends(get_email_notifier),
) -> PasswordResetResponse:
    service = _service(session, settings, email_notifier)
    user, temporary = await service.reset_password(
        user_id=user_id, actor_id=actor.id, ip=get_client_ip(request)
    )
    return PasswordResetResponse(
        user_id=user.id,
        email=user.email,
        temporary_password=temporary,
    )


@router.post("/{user_id}/roles", response_model=UserOut, summary="Назначить роли")
async def assign_roles(
    user_id: int,
    payload: UserRolesAssign,
    request: Request,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_admin_only),
    email_notifier: EmailNotifier = Depends(get_email_notifier),
) -> UserOut:
    service = _service(session, settings, email_notifier)
    user = await service.assign_roles(
        user_id=user_id,
        role_names=payload.role_names,
        actor_id=actor.id,
        ip=get_client_ip(request),
    )
    return _to_out(user)
