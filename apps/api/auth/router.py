"""Auth-роутер: /auth/login, /auth/refresh, /auth/logout (FR-AUTH-04, 07)."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from apps.api.auth.schemas import LoginRequest, LogoutRequest, RefreshRequest, TokenPair
from apps.api.auth.service import AuthService
from apps.api.deps import (
    BruteForceDep,
    CurrentUserDep,
    DBSession,
    RefreshStoreDep,
    RevocationDep,
    SettingsDep,
    get_client_ip,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _service(
    session: DBSession,
    settings: SettingsDep,
    bf: BruteForceDep,
    revocation: RevocationDep,
    refresh_store: RefreshStoreDep,
) -> AuthService:
    return AuthService(
        session=session,
        settings=settings,
        bruteforce=bf,
        revocation=revocation,
        refresh_store=refresh_store,
    )


@router.post("/login", response_model=TokenPair, summary="Войти и получить токены")
async def login(
    payload: LoginRequest,
    request: Request,
    session: DBSession,
    settings: SettingsDep,
    bf: BruteForceDep,
    revocation: RevocationDep,
    refresh_store: RefreshStoreDep,
) -> TokenPair:
    service = _service(session, settings, bf, revocation, refresh_store)
    return await service.login(
        email=payload.email, password=payload.password, ip=get_client_ip(request)
    )


@router.post("/refresh", response_model=TokenPair, summary="Обновить пару токенов")
async def refresh(
    payload: RefreshRequest,
    session: DBSession,
    settings: SettingsDep,
    bf: BruteForceDep,
    revocation: RevocationDep,
    refresh_store: RefreshStoreDep,
) -> TokenPair:
    service = _service(session, settings, bf, revocation, refresh_store)
    return await service.refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_200_OK, summary="Выйти из системы")
async def logout(
    payload: LogoutRequest,
    request: Request,
    user: CurrentUserDep,
    session: DBSession,
    settings: SettingsDep,
    bf: BruteForceDep,
    revocation: RevocationDep,
    refresh_store: RefreshStoreDep,
) -> dict[str, str]:
    service = _service(session, settings, bf, revocation, refresh_store)
    await service.logout(
        access_jti=user.jti,
        access_ttl_seconds=user.exp_seconds,
        refresh_token=payload.refresh_token,
        user_id=user.id,
        ip=get_client_ip(request),
    )
    return {"status": "logged_out"}
