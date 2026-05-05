"""Бизнес-логика администрирования пользователей (FR-AUTH-01, 02, 06)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.email import EmailNotifier
from apps.api.auth.passwords import generate_temporary_password, hash_password
from apps.api.config import Settings
from apps.api.db.models import AuditAction, Role, User, UserRole
from apps.api.db.repositories.users import UserRepository
from apps.api.errors import Conflict, NotFound, ValidationFailed
from apps.api.services.audit import AuditService


class UserService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        email_notifier: EmailNotifier,
    ) -> None:
        self._session = session
        self._settings = settings
        self._email = email_notifier
        self._users = UserRepository(session)
        self._audit = AuditService(session)

    async def _resolve_role_ids(self, role_names: list[str]) -> list[Role]:
        if not role_names:
            return []
        stmt = select(Role).where(Role.name.in_(role_names))
        result = await self._session.execute(stmt)
        roles = list(result.scalars().all())
        found = {r.name for r in roles}
        missing = set(role_names) - found
        if missing:
            raise ValidationFailed(f"Неизвестные роли: {', '.join(sorted(missing))}.")
        return roles

    async def create(
        self,
        *,
        email: str,
        full_name: str | None,
        password: str,
        role_names: list[str],
        actor_id: int,
        ip: str,
    ) -> User:
        roles = await self._resolve_role_ids(role_names)
        user = User(
            email=email.lower(),
            full_name=full_name,
            password_hash=hash_password(password, cost=self._settings.bcrypt_cost_factor),
        )
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise Conflict("Пользователь с таким email уже существует.") from exc
        for role in roles:
            self._session.add(UserRole(user_id=user.id, role_id=role.id))
        await self._audit.record(
            AuditAction.USER_CREATED,
            user_id=actor_id,
            target_user_id=user.id,
            ip_address=ip,
            details={"role_names": role_names},
        )
        await self._session.commit()
        await self._session.refresh(user, attribute_names=["roles"])
        return user

    async def update(
        self,
        *,
        user_id: int,
        full_name: str | None,
        is_active: bool | None,
        actor_id: int,
        ip: str,
    ) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFound("Пользователь не найден.")
        if full_name is not None:
            user.full_name = full_name
        if is_active is not None:
            user.is_active = is_active
        await self._audit.record(
            AuditAction.USER_EDITED,
            user_id=actor_id,
            target_user_id=user.id,
            ip_address=ip,
            details={"full_name_changed": full_name is not None, "is_active_changed": is_active is not None},
        )
        await self._session.commit()
        return user

    async def deactivate(self, *, user_id: int, actor_id: int, ip: str) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFound("Пользователь не найден.")
        user.is_active = False
        # FR-DB-06: сценарии деактивированного пользователя переписываются на актора-админа.
        from apps.api.db.models import Script  # локальный импорт, чтобы избежать цикла на старте

        from sqlalchemy import update

        await self._session.execute(
            update(Script)
            .where(Script.created_by_user_id == user_id)
            .values(created_by_user_id=actor_id)
        )
        await self._audit.record(
            AuditAction.USER_DEACTIVATED,
            user_id=actor_id,
            target_user_id=user.id,
            ip_address=ip,
        )
        await self._session.commit()
        return user

    async def reset_password(
        self, *, user_id: int, actor_id: int, ip: str
    ) -> tuple[User, str]:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFound("Пользователь не найден.")
        temporary = generate_temporary_password()
        user.password_hash = hash_password(temporary, cost=self._settings.bcrypt_cost_factor)
        user.must_change_password = True
        user.failed_login_count = 0
        user.locked_until = None
        await self._email.send_password_reset(
            to_email=user.email,
            temporary_password=temporary,
            user_id=user.id,
        )
        await self._audit.record(
            AuditAction.PASSWORD_RESET,
            user_id=actor_id,
            target_user_id=user.id,
            ip_address=ip,
        )
        await self._session.commit()
        return user, temporary

    async def assign_roles(
        self, *, user_id: int, role_names: list[str], actor_id: int, ip: str
    ) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFound("Пользователь не найден.")
        roles = await self._resolve_role_ids(role_names)
        existing_ids = {r.id for r in user.roles}
        for role in roles:
            if role.id not in existing_ids:
                self._session.add(UserRole(user_id=user.id, role_id=role.id))
        await self._audit.record(
            AuditAction.ROLE_ASSIGNED,
            user_id=actor_id,
            target_user_id=user.id,
            ip_address=ip,
            details={"role_names": role_names},
        )
        await self._session.commit()
        await self._session.refresh(user, attribute_names=["roles"])
        return user
