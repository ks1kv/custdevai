"""bcrypt-хеширование паролей с обязательным cost factor ≥ 12 (FR-AUTH-03, NFR-SEC-02)."""

from __future__ import annotations

import secrets
import string

import bcrypt

MIN_COST = 12


def hash_password(plain: str, *, cost: int) -> str:
    """Хешировать пароль bcrypt-ом.

    Args:
        plain: Открытый пароль.
        cost: bcrypt cost factor; должен быть ≥ 12 (NFR-SEC-02).

    Returns:
        Строковый bcrypt-хеш длиной 60 символов.

    Raises:
        ValueError: если cost < 12 — fail-fast, чтобы исключить случайное
            ослабление политики хеширования.
    """
    if cost < MIN_COST:
        raise ValueError(
            f"bcrypt cost factor должен быть не ниже {MIN_COST} (NFR-SEC-02), получено {cost}"
        )
    salt = bcrypt.gensalt(rounds=cost)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Проверить пароль против хеша. Возвращает False для повреждённого хеша."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def generate_temporary_password(length: int = 16) -> str:
    """Сгенерировать криптостойкий временный пароль для сброса админом (FR-AUTH-06)."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))
