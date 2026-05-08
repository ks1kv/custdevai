"""Псевдонимизация респондентов для отчётов (FR-DB-03 + FR-RPT-05).

Phase 4: производный псевдоним из `session.id % 10000` (Q1 решение
пользователя) — без миграции БД и без race-condition в hot-path бота.
Внутри одной кампании коллизий нет (session.id уникален). Между разными
кампаниями возможна коллизия при > 10 000 сессий — это допустимо для MVP
и решается переходом на `pseudonym_ordinal SMALLINT` в Phase 5.

Telegram ID никогда не участвует в псевдониме (FR-BOT-10) — только
session.id, который сам не является ПДн.
"""

from __future__ import annotations


def session_to_pseudonym(session_id: int) -> str:
    """Сформировать псевдоним вида 'R-NNNN' для отображения в отчётах.

    Args:
        session_id: первичный ключ InterviewSession (BIGINT > 0).

    Returns:
        Строка длиной 6 символов: 'R-' + 4 цифры.

    Raises:
        ValueError: если session_id ≤ 0.
    """
    if session_id <= 0:
        raise ValueError("session_id должен быть положительным")
    return f"R-{session_id % 10000:04d}"
