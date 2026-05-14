"""Unit-тесты EmailNotifier-фабрики (FR-AUTH-06)."""

from __future__ import annotations

import pytest

from apps.api.auth.email import (
    LoggingEmailNotifier,
    SMTPEmailNotifier,
    get_email_notifier,
)
from apps.api.config import Settings


def _make_settings(**overrides) -> Settings:
    base = {
        "postgres_password": "x" * 32,
        "jwt_secret": "y" * 32,
        "pseudonym_master_salt": "z" * 64,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[call-arg]


class TestEmailNotifierFactory:
    def test_returns_logging_when_smtp_not_configured(self) -> None:
        settings = _make_settings(smtp_host="", smtp_from="")
        notifier = get_email_notifier(settings)
        assert isinstance(notifier, LoggingEmailNotifier)

    def test_returns_smtp_when_configured(self) -> None:
        settings = _make_settings(
            smtp_host="mail.example.com",
            smtp_port=587,
            smtp_username="user",
            smtp_password="pwd",
            smtp_from="noreply@example.com",
        )
        notifier = get_email_notifier(settings)
        assert isinstance(notifier, SMTPEmailNotifier)

    def test_returns_logging_when_only_host_no_from(self) -> None:
        # Без SMTP_FROM шлём как Logging — иначе сообщение без заголовка From.
        settings = _make_settings(smtp_host="mail.example.com", smtp_from="")
        assert isinstance(get_email_notifier(settings), LoggingEmailNotifier)


@pytest.mark.asyncio
class TestLoggingEmailNotifier:
    async def test_send_password_reset_does_not_raise(self) -> None:
        notifier = LoggingEmailNotifier()
        # Просто проверка отсутствия исключения и того, что метод
        # не возвращает значение.
        result = await notifier.send_password_reset(
            to_email="user@example.com",
            temporary_password="never-logged",
            user_id=42,
        )
        assert result is None
