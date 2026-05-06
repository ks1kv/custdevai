"""Интерфейс отправки email-уведомлений (FR-AUTH-06).

Реальная SMTP-реализация добавлена в Phase 5. На Phase 1 — только
LoggingEmailNotifier, пишущий тело письма в structured-лог.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class EmailNotifier(Protocol):
    """Контракт уведомителя; внедряется в UserService для FR-AUTH-06."""

    async def send_password_reset(
        self, *, to_email: str, temporary_password: str, user_id: int
    ) -> None: ...


class LoggingEmailNotifier:
    """Phase 1: пишет факт отправки в лог с заглушкой содержимого."""

    async def send_password_reset(
        self, *, to_email: str, temporary_password: str, user_id: int
    ) -> None:
        # Сам пароль никогда не выводится в лог — только маркер «отправлено».
        logger.info(
            "Password reset email queued",
            extra={
                "to_email": to_email,
                "user_id": user_id,
                "smtp_implementation_pending": True,
            },
        )
