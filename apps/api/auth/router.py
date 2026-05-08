"""Auth-роутер: /auth/login, /auth/refresh, /auth/logout (FR-AUTH-04, 07).

Phase 4: добавлена опциональная установка httpOnly cookies для SPA
через query-param `?set_cookie=true` (по умолчанию). Cookies:
  * access_token — Path=/api, Max-Age = jwt_access_token_ttl_minutes * 60;
  * refresh_token — Path=/api/v1/auth, Max-Age = jwt_refresh_token_ttl_days * 86400.
SameSite=Strict + Secure (в production) — защита от XSRF/MITM.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Request, Response, status

from apps.api.auth.schemas import LoginRequest, LogoutRequest, RefreshRequest, TokenPair
from apps.api.auth.service import AuthService
from apps.api.config import Settings
from apps.api.deps import (
    BruteForceDep,
    CurrentUserDep,
    DBSession,
    RefreshStoreDep,
    RevocationDep,
    SettingsDep,
    get_client_ip,
)
from apps.api.errors import AuthenticationFailed

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"
_ACCESS_COOKIE_PATH = "/api"
_REFRESH_COOKIE_PATH = "/api/v1/auth"


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


def _set_auth_cookies(
    response: Response, *, tokens: TokenPair, settings: Settings
) -> None:
    """Установить httpOnly cookies для SPA (Phase 4)."""
    access_max_age = settings.jwt_access_token_ttl_minutes * 60
    refresh_max_age = settings.jwt_refresh_token_ttl_days * 86400
    secure = settings.effective_cookie_secure
    samesite = settings.cookie_samesite
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=tokens.access_token,
        max_age=access_max_age,
        httponly=True,
        secure=secure,
        samesite=samesite,  # type: ignore[arg-type]
        path=_ACCESS_COOKIE_PATH,
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=tokens.refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=secure,
        samesite=samesite,  # type: ignore[arg-type]
        path=_REFRESH_COOKIE_PATH,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE_NAME, path=_ACCESS_COOKIE_PATH)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=_REFRESH_COOKIE_PATH)


@router.post("/login", response_model=TokenPair, summary="Войти и получить токены")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DBSession,
    settings: SettingsDep,
    bf: BruteForceDep,
    revocation: RevocationDep,
    refresh_store: RefreshStoreDep,
    set_cookie: bool = Query(default=False, alias="set_cookie"),
) -> TokenPair:
    service = _service(session, settings, bf, revocation, refresh_store)
    tokens = await service.login(
        email=payload.email, password=payload.password, ip=get_client_ip(request)
    )
    if set_cookie:
        _set_auth_cookies(response, tokens=tokens, settings=settings)
    return tokens


@router.post("/refresh", response_model=TokenPair, summary="Обновить пару токенов")
async def refresh(
    payload: RefreshRequest | None,
    response: Response,
    session: DBSession,
    settings: SettingsDep,
    bf: BruteForceDep,
    revocation: RevocationDep,
    refresh_store: RefreshStoreDep,
    cookie_refresh: Annotated[
        str | None, Cookie(alias=REFRESH_COOKIE_NAME)
    ] = None,
    set_cookie: bool = Query(default=False, alias="set_cookie"),
) -> TokenPair:
    """Принимает refresh-токен из тела или из cookie (если SPA)."""
    refresh_token = (payload.refresh_token if payload is not None else None) or cookie_refresh
    if not refresh_token:
        raise AuthenticationFailed("Не передан refresh-токен.")
    service = _service(session, settings, bf, revocation, refresh_store)
    tokens = await service.refresh(refresh_token)
    if set_cookie:
        _set_auth_cookies(response, tokens=tokens, settings=settings)
    return tokens


@router.post("/logout", status_code=status.HTTP_200_OK, summary="Выйти из системы")
async def logout(
    payload: LogoutRequest | None,
    request: Request,
    response: Response,
    user: CurrentUserDep,
    session: DBSession,
    settings: SettingsDep,
    bf: BruteForceDep,
    revocation: RevocationDep,
    refresh_store: RefreshStoreDep,
    cookie_refresh: Annotated[
        str | None, Cookie(alias=REFRESH_COOKIE_NAME)
    ] = None,
) -> dict[str, str]:
    service = _service(session, settings, bf, revocation, refresh_store)
    refresh_token = None
    if payload is not None:
        refresh_token = payload.refresh_token
    refresh_token = refresh_token or cookie_refresh
    await service.logout(
        access_jti=user.jti,
        access_ttl_seconds=user.exp_seconds,
        refresh_token=refresh_token,
        user_id=user.id,
        ip=get_client_ip(request),
    )
    _clear_auth_cookies(response)
    return {"status": "logged_out"}
