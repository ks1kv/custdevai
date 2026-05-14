"""Интерфейс отправки email-уведомлений (FR-AUTH-06).

Phase 1 — LoggingEmailNotifier (только запись в лог).
Phase 5 — SMTPEmailNotifier поверх aiosmtplib + фабрика
`get_email_notifier()`, которая выбирает реализацию по Settings:

  - SMTP_HOST задан → SMTPEmailNotifier (production-режим);
  - иначе → LoggingEmailNotifier (dev, тесты).

При сбое SMTP подсистема НЕ прерывает reset_password: исключение
ловится в send_password_reset(), пишется audit-запись с пометкой
delivery_failed=True, временный пароль возвращается админу.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage
from typing import Protocol

from apps.api.config import Settings

logger = logging.getLogger(__name__)


class EmailNotifier(Protocol):
    """Контракт уведомителя; внедряется в UserService для FR-AUTH-06."""

    async def send_password_reset(
        self, *, to_email: str, temporary_password: str, user_id: int
    ) -> None: ...


class LoggingEmailNotifier:
    """Записывает факт отправки в лог без реальной доставки."""

    async def send_password_reset(
        self, *, to_email: str, temporary_password: str, user_id: int
    ) -> None:
        # Сам пароль никогда не выводится в лог — только маркер «отправлено».
        del temporary_password  # явно отбрасываем — в production не хранится
        logger.info(
            "password_reset_email_logged",
            extra={
                "to_email": to_email,
                "user_id": user_id,
                "delivery": "logging-stub",
            },
        )


class SMTPEmailNotifier:
    """Phase 5: реальная доставка через aiosmtplib (FR-AUTH-06).

    Конфигурация — Settings.smtp_*. Отправка plain-text сообщения на
    русском. STARTTLS включается через smtp_use_tls=True (default).

    Поскольку SMTP-серверы могут быть недоступны, исключения не
    пробрасываются наверх — пишется warning-лог. Это допустимо: после
    reset_password() админ получает временный пароль другим каналом
    (например, лично) и может ретраить отправку отдельно.
    """

    def __init__(self, settings: Settings) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._username = settings.smtp_username
        self._password = settings.smtp_password
        self._from = settings.smtp_from
        self._use_tls = settings.smtp_use_tls

    async def send_password_reset(
        self, *, to_email: str, temporary_password: str, user_id: int
    ) -> None:
        msg = EmailMessage()
        msg["Subject"] = "Сброс пароля CustDevAI"
        msg["From"] = self._from
        msg["To"] = to_email
        msg.set_content(
            "Здравствуйте!\n\n"
            "Ваш пароль для входа в панель CustDevAI был сброшен "
            "администратором.\n\n"
            f"Временный пароль: {temporary_password}\n\n"
            "При первом входе система потребует установить новый пароль.\n\n"
            "Если вы не запрашивали сброс, немедленно свяжитесь с администратором "
            "вашей организации.\n\n"
            "— Команда CustDevAI",
            charset="utf-8",
        )
        try:
            await self._send(msg)
            logger.info(
                "password_reset_email_sent",
                extra={"to_email": to_email, "user_id": user_id, "delivery": "smtp"},
            )
        except Exception:  # pragma: no cover — сетевые сбои
            # SMTP failure не блокирует reset_password (NFR-SEC-05 spirit).
            logger.exception(
                "password_reset_email_failed",
                extra={
                    "to_email": to_email,
                    "user_id": user_id,
                    "delivery_failed": True,
                },
            )

    async def _send(self, msg: EmailMessage) -> None:
        # Импорт aiosmtplib отложенный — он не нужен в LoggingEmailNotifier
        # и не должен быть жёсткой зависимостью dev/тестов.
        import aiosmtplib  # type: ignore[import-not-found]

        await aiosmtplib.send(
            msg,
            hostname=self._host,
            port=self._port,
            username=self._username or None,
            password=self._password or None,
            start_tls=self._use_tls,
        )


def get_email_notifier(settings: Settings) -> EmailNotifier:
    """Фабрика уведомителя. SMTP в production, Logging иначе.

    Поведение по умолчанию: если SMTP_HOST не задан — Logging stub.
    Это безопасно для dev и тестов (никаких сетевых вызовов).
    В production .env обязательно ставит SMTP_HOST.
    """
    if settings.smtp_host and settings.smtp_from:
        return SMTPEmailNotifier(settings)
    return LoggingEmailNotifier()
