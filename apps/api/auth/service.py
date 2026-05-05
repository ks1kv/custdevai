"""Бизнес-логика аутентификации: login / refresh / logout."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.bruteforce import (
    BruteForceGuard,
    RefreshTokenStore,
    TokenRevocationStore,
)
from apps.api.auth.jwt import TokenPayload, TokenType, decode_token, issue_token_pair
from apps.api.auth.passwords import verify_password
from apps.api.auth.schemas import TokenPair
from apps.api.config import Settings
from apps.api.db.models import AuditAction
from apps.api.db.repositories.users import UserRepository
from apps.api.errors import AuthenticationFailed, RateLimited
from apps.api.services.audit import AuditService


class AuthService:
    """Оркестратор всего auth-flow.

    Зависимости вкручиваются явно — это упрощает тестирование с моками.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        bruteforce: BruteForceGuard,
        revocation: TokenRevocationStore,
        refresh_store: RefreshTokenStore,
    ) -> None:
        self._session = session
        self._settings = settings
        self._bf = bruteforce
        self._revocation = revocation
        self._refresh_store = refresh_store
        self._users = UserRepository(session)
        self._audit = AuditService(session)

    async def login(self, *, email: str, password: str, ip: str) -> TokenPair:
        if await self._bf.is_locked(ip):
            raise RateLimited("Слишком много неудачных попыток входа. Попробуйте через 15 минут.")
        user = await self._users.get_by_email(email)
        if user is None or not user.is_active:
            await self._record_failed(ip=ip, target_user_id=None)
            raise AuthenticationFailed("Неверный email или пароль.")
        if not verify_password(password, user.password_hash):
            await self._record_failed(ip=ip, target_user_id=user.id)
            raise AuthenticationFailed("Неверный email или пароль.")

        await self._bf.reset(ip)
        roles = await self._users.get_role_names(user.id)
        access, refresh, _, refresh_jti = issue_token_pair(
            user_id=user.id, roles=roles, settings=self._settings
        )
        await self._refresh_store.remember(
            refresh_jti,
            user.id,
            ttl_seconds=self._settings.jwt_refresh_token_ttl_days * 86400,
        )
        await self._audit.record(
            AuditAction.LOGIN_SUCCESSFUL,
            user_id=user.id,
            target_user_id=user.id,
            ip_address=ip,
        )
        await self._session.commit()
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            must_change_password=user.must_change_password,
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        payload: TokenPayload = decode_token(refresh_token, settings=self._settings)
        if payload.type is not TokenType.REFRESH:
            raise AuthenticationFailed("Ожидался refresh-токен.")
        if await self._revocation.is_revoked(payload.jti):
            raise AuthenticationFailed("Refresh-токен отозван.")
        if not await self._refresh_store.consume(payload.jti):
            raise AuthenticationFailed("Refresh-токен уже использован или истёк.")
        # Старый jti — в deny-list до истечения exp.
        ttl_seconds = self._remaining_seconds(payload)
        await self._revocation.revoke(payload.jti, ttl_seconds=ttl_seconds)

        user = await self._users.get_by_id(payload.sub)
        if user is None or not user.is_active:
            raise AuthenticationFailed("Учётная запись недоступна.")
        roles = await self._users.get_role_names(user.id)
        access, refresh, _, new_refresh_jti = issue_token_pair(
            user_id=user.id, roles=roles, settings=self._settings
        )
        await self._refresh_store.remember(
            new_refresh_jti,
            user.id,
            ttl_seconds=self._settings.jwt_refresh_token_ttl_days * 86400,
        )
        await self._session.commit()
        return TokenPair(access_token=access, refresh_token=refresh)

    async def logout(
        self,
        *,
        access_jti: str,
        access_ttl_seconds: int,
        refresh_token: str | None,
        user_id: int,
        ip: str,
    ) -> None:
        await self._revocation.revoke(access_jti, ttl_seconds=access_ttl_seconds)
        if refresh_token:
            try:
                rp = decode_token(refresh_token, settings=self._settings)
                if rp.type is TokenType.REFRESH:
                    await self._refresh_store.consume(rp.jti)
                    await self._revocation.revoke(rp.jti, ttl_seconds=self._remaining_seconds(rp))
            except AuthenticationFailed:
                # logout-идемпотентен: невалидный refresh не должен 401-ить.
                pass
        await self._audit.record(
            AuditAction.LOGOUT,
            user_id=user_id,
            target_user_id=user_id,
            ip_address=ip,
        )
        await self._session.commit()

    async def _record_failed(self, *, ip: str, target_user_id: int | None) -> None:
        locked = await self._bf.register_failure(ip)
        await self._audit.record(
            AuditAction.LOGIN_FAILED,
            target_user_id=target_user_id,
            ip_address=ip,
            details={"locked": locked},
        )
        await self._session.commit()

    @staticmethod
    def _remaining_seconds(payload: TokenPayload) -> int:
        delta: timedelta = payload.exp - payload.iat
        return max(0, int(delta.total_seconds()))
