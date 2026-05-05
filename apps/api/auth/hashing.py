"""Псевдонимизация Telegram-идентификаторов (FR-DB-03, NFR-SEC-08).

SHA-256 хеш telegram_id со специфичной для каждой кампании солью
исключает возможность связать одного и того же респондента между
разными кампаниями. Сама соль выводится из мастер-соли деплоя через
HKDF-SHA256, что даёт 32-байтную, детерминированную, независимую от
campaign_id соль.
"""

from __future__ import annotations

import hashlib
import hmac
import os


def derive_campaign_salt(*, master_salt_hex: str, campaign_id: int) -> bytes:
    """HKDF-Expand на единственном шаге, info = b"custdevai:campaign:{id}".

    Сжимаем мастер-соль до 32 байт через HMAC-SHA256, чем дальше детерминированно
    выводим per-campaign соль. На выходе всегда 32 байта.
    """
    master = bytes.fromhex(master_salt_hex)
    if len(master) < 16:
        raise ValueError(
            "PSEUDONYM_MASTER_SALT слишком короткая: требуется минимум 32 hex-символа."
        )
    info = f"custdevai:campaign:{campaign_id}".encode("utf-8")
    # HKDF-Expand для одного 32-байтного блока: T(1) = HMAC(prk, info || 0x01).
    return hmac.new(master, info + b"\x01", hashlib.sha256).digest()


def random_campaign_salt() -> bytes:
    """Альтернативная соль из CSPRNG, если деривация не подходит контексту."""
    return os.urandom(32)


def hash_telegram_id(telegram_id: int, salt: bytes) -> bytes:
    """Вернуть SHA-256(salt || telegram_id_bytes) — 32 байта.

    telegram_id кодируется как ASCII-строка десятичного представления, что
    эквивалентно тому, как он приходит из Telegram Bot API, и не зависит от
    байтового порядка целочисленного представления.
    """
    if len(salt) != 32:
        raise ValueError("Соль должна быть длиной ровно 32 байта.")
    h = hashlib.sha256()
    h.update(salt)
    h.update(str(telegram_id).encode("ascii"))
    return h.digest()
