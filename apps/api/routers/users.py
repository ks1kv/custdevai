"""Admin-only управление пользователями (FR-AUTH-01, 02, 06)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from apps.api.auth.email import EmailNotifier
from apps.api.auth.rbac import Role
from apps.api.db.models import User
from apps.api.deps import (
    CurrentUser,
    CurrentUserDep,
    DBSession,
    SettingsDep,
    get_client_ip,
    require_roles,
)
from apps.api.schemas.user import (
    MyProfileUpdate,
    PasswordResetResponse,
    UserCreate,
    UserOut,
    UserRolesAssign,
    UserUpdate,
)
from apps.api.services.users import UserService

router = APIRouter(prefix="/users", tags=["users"])

_admin_only = require_roles(Role.ADMIN)


def get_email_notifier(settings: SettingsDep) -> EmailNotifier:
    """Phase 5: фабрика выбирает SMTPEmailNotifier при наличии SMTP_HOST,
    иначе LoggingEmailNotifier (dev/tests).
    """
    from apps.api.auth.email import get_email_notifier as factory

    return factory(settings)


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
        researcher_telegram_chat_id=user.researcher_telegram_chat_id,
        roles=[r.name for r in (user.roles or [])],
    )


@router.get(
    "/me",
    response_model=UserOut,
    summary="Профиль текущего пользователя",
)
async def get_me(
    session: DBSession,
    actor: CurrentUserDep,
) -> UserOut:
    from apps.api.db.repositories.users import UserRepository

    repo = UserRepository(session)
    user = await repo.get_by_id(actor.id)
    if user is None:
        from apps.api.errors import NotFound

        raise NotFound("Пользователь не найден.")
    await session.refresh(user, attribute_names=["roles"])
    return _to_out(user)


@router.patch(
    "/me",
    response_model=UserOut,
    summary="Обновить свой профиль (full_name, telegram chat_id)",
)
async def update_me(
    payload: MyProfileUpdate,
    session: DBSession,
    actor: CurrentUserDep,
) -> UserOut:
    """FR-BOT-09 закрытие: исследователь регистрирует свой telegram chat_id
    через self-update; после этого второй push после ML-анализа реально
    доставляется."""
    from apps.api.db.repositories.users import UserRepository
    from apps.api.errors import NotFound

    repo = UserRepository(session)
    user = await repo.get_by_id(actor.id)
    if user is None:
        raise NotFound("Пользователь не найден.")
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.researcher_telegram_chat_id is not None:
        user.researcher_telegram_chat_id = payload.researcher_telegram_chat_id
    await session.commit()
    await session.refresh(user, attribute_names=["roles"])
    return _to_out(user)


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
