"""Парсер payload-а Telegram deep-link для FR-BOT-01.

Формат: https://t.me/<botname>?start=c<campaign_id>
Telegram передаёт <campaign_id> как первый аргумент команды /start.

Без HMAC по решению Phase 2: защита через `Campaign.status == RUNNING`.
Если ссылка ведёт на не-running кампанию — бот отвечает мягким
сообщением и не создаёт сессию.
"""

from __future__ import annotations

import re

# c<digits>, без других символов. Длина campaign_id BIGINT — до 19 знаков.
_PAYLOAD_RE = re.compile(r"^c(\d{1,19})$")


class InvalidDeepLink(ValueError):
    """payload неконсистентен с ожидаемым форматом."""


def parse_campaign_id(payload: str | None) -> int:
    """Извлечь campaign_id из payload вида 'c123'.

    Args:
        payload: строка после `/start ` (может быть None).

    Returns:
        целочисленный campaign_id.

    Raises:
        InvalidDeepLink: payload пустой/отсутствует/не подходит под шаблон.
    """
    if not payload:
        raise InvalidDeepLink("payload отсутствует")
    match = _PAYLOAD_RE.match(payload.strip())
    if match is None:
        raise InvalidDeepLink(f"payload не соответствует шаблону c<id>: {payload!r}")
    return int(match.group(1))


def build_payload(campaign_id: int) -> str:
    """Обратная функция для генерации invitation_url исследователем."""
    if campaign_id <= 0:
        raise ValueError("campaign_id должен быть положительным")
    return f"c{campaign_id}"
