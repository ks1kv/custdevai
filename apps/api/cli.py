"""CLI-команды CustDevAI API.

На Phase 1 предоставлена единственная команда — create-admin, которая
позволяет завести первого администратора после первого деплоя
(bootstrap), не открывая публичной регистрации.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from apps.api.auth.passwords import hash_password
from apps.api.config import get_settings
from apps.api.db.models import AuditAction, Role, User, UserRole
from apps.api.db.session import get_sessionmaker
from apps.api.services.audit import AuditService

logger = logging.getLogger(__name__)


async def _create_admin(email: str, password: str, full_name: str | None) -> None:
    settings = get_settings()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        existing = await session.execute(select(User).where(User.email == email.lower()))
        if existing.scalar_one_or_none() is not None:
            print(f"Пользователь с email {email} уже существует.", file=sys.stderr)
            sys.exit(2)

        admin_role_q = await session.execute(select(Role).where(Role.name == "Admin"))
        admin_role = admin_role_q.scalar_one_or_none()
        if admin_role is None:
            print(
                "Роль Admin не найдена. Сначала примените миграции: "
                "alembic upgrade head.",
                file=sys.stderr,
            )
            sys.exit(3)

        user = User(
            email=email.lower(),
            full_name=full_name,
            password_hash=hash_password(password, cost=settings.bcrypt_cost_factor),
            must_change_password=True,
        )
        session.add(user)
        await session.flush()
        session.add(UserRole(user_id=user.id, role_id=admin_role.id))
        await AuditService(session).record(
            AuditAction.USER_CREATED,
            user_id=user.id,
            target_user_id=user.id,
            details={"bootstrap": True, "role": "Admin"},
        )
        await session.commit()
        print(
            f"Админ создан: id={user.id}, email={user.email}. "
            "Флаг must_change_password=True — смените пароль при первом входе."
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="apps.api.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create_admin = sub.add_parser("create-admin", help="Создать первого администратора")
    create_admin.add_argument("--email", required=True)
    create_admin.add_argument("--password", required=True)
    create_admin.add_argument("--full-name", default=None)

    args = parser.parse_args(argv)
    if args.command == "create-admin":
        asyncio.run(_create_admin(args.email, args.password, args.full_name))


if __name__ == "__main__":
    main()
