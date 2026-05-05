"""RBAC: enum ролей и FastAPI-зависимости для проверки прав (FR-AUTH-02, FR-AUTH-05)."""

from __future__ import annotations

import enum
from collections.abc import Iterable

from apps.api.errors import PermissionDenied


class Role(str, enum.Enum):
    """Четыре роли, заведённые seed-вставкой в миграции 0001."""

    ADMIN = "Admin"
    RESEARCHER = "Researcher"
    ANALYST = "Analyst"
    RESPONDENT = "Respondent"


def require(roles: Iterable[Role], user_roles: Iterable[str]) -> None:
    """Проверить, что среди ролей пользователя есть хотя бы одна разрешённая.

    Args:
        roles: допустимые роли для операции.
        user_roles: имена ролей текущего пользователя (из JWT).

    Raises:
        PermissionDenied: если пересечения нет.
    """
    allowed = {r.value for r in roles}
    if not (allowed & set(user_roles)):
        raise PermissionDenied(
            "Недостаточно прав для выполнения операции."
        )
