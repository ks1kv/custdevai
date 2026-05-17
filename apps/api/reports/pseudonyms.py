"""Псевдонимизация респондентов для отчётов (FR-DB-03 + FR-RPT-05).

Псевдоним R-NNNN детерминированно выводится из `telegram_id_hash` сессии.
`telegram_id_hash` уже представляет собой SHA-256(telegram_id || campaign.pseudonym_salt),
поэтому полученный R-NNNN автоматически уникален в пределах кампании
(один и тот же респондент → один и тот же псевдоним внутри кампании;
тот же telegram_id в другой кампании → другой псевдоним, потому что
соль кампании другая).

Telegram ID никогда не участвует в псевдониме напрямую (FR-BOT-10) —
только через одностороннюю SHA-256-цепочку.
"""

from __future__ import annotations

import struct

_PSEUDONYM_HASH_PREFIX_BYTES = 4
_PSEUDONYM_SPACE = 10_000


def session_to_pseudonym(telegram_id_hash: bytes) -> str:
    """Сформировать псевдоним вида 'R-NNNN' из SHA-256-хеша Telegram ID.

    Args:
        telegram_id_hash: 32-байтовый SHA-256 от `telegram_id || pseudonym_salt`,
            хранится в `interview_sessions.telegram_id_hash`.

    Returns:
        Строка длиной 6 символов: 'R-' + 4 десятичные цифры.

    Raises:
        ValueError: если хеш короче 4 байт (битый или подменён).
    """
    if not isinstance(telegram_id_hash, bytes | bytearray | memoryview):
        raise TypeError("telegram_id_hash должен быть bytes-like")
    if len(telegram_id_hash) < _PSEUDONYM_HASH_PREFIX_BYTES:
        raise ValueError(
            f"telegram_id_hash должен быть не короче {_PSEUDONYM_HASH_PREFIX_BYTES} байт"
        )
    prefix = bytes(telegram_id_hash[:_PSEUDONYM_HASH_PREFIX_BYTES])
    number = struct.unpack(">I", prefix)[0] % _PSEUDONYM_SPACE
    return f"R-{number:04d}"
