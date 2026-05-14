"""Парсер payload-а Telegram deep-link для FR-BOT-01.

Формат: `https://t.me/<botname>?start=<payload>`

Phase 5 ввёл HMAC-подпись:
  payload = c<campaign_id>.<sig>
  sig     = base32(hmac_sha256(b"deeplink|" + str(campaign_id),
                               HKDF(pseudonym_master_salt, info=b"deeplink"))[:10])

Старый формат без подписи `c<campaign_id>` продолжаем принимать с
DeprecationWarning в логе — миграция мягкая, чтобы старые скриншоты
ссылок из Phase 1–4 продолжали работать. На Phase 6 (после переходного
периода) старый формат можно отключить.

Защита от подбора campaign_id (NFR-SEC-08): даже зная схему, без знания
master-salt невозможно сгенерировать валидную подпись.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re

logger = logging.getLogger(__name__)

# Старый формат (без подписи). Length campaign_id BIGINT — до 19 знаков.
_LEGACY_RE = re.compile(r"^c(\d{1,19})$")
# Новый формат: c<digits>.<base32 16-символов без padding>.
# base32 от 10 байт = 16 символов A-Z2-7.
_SIGNED_RE = re.compile(r"^c(\d{1,19})\.([A-Z2-7]{16})$")

_SIG_BYTES = 10  # 80 бит → достаточно против brute-force, payload короткий.
_HKDF_INFO = b"deeplink"


class InvalidDeepLink(ValueError):
    """payload неконсистентен с ожидаемым форматом."""


def _derive_secret(master_salt: str) -> bytes:
    """Получить секрет для подписи из PSEUDONYM_MASTER_SALT через HKDF-Expand.

    Используется тот же master-salt, что и для псевдонимизации Telegram ID,
    но с другим info-тегом — это даёт криптографически независимый ключ.
    """
    if not master_salt:
        raise ValueError("master_salt не задан")
    # PSEUDONYM_MASTER_SALT хранится как hex; декодируем в bytes.
    try:
        master_bytes = bytes.fromhex(master_salt)
    except ValueError:
        master_bytes = master_salt.encode("utf-8")
    # HKDF-Expand без отдельного Extract (т.к. master уже считается ключом).
    # Один блок 32 байта.
    prk = master_bytes
    t = hmac.new(prk, _HKDF_INFO + b"\x01", hashlib.sha256).digest()
    return t


def _sign(campaign_id: int, master_salt: str) -> str:
    secret = _derive_secret(master_salt)
    raw = hmac.new(secret, f"deeplink|{campaign_id}".encode(), hashlib.sha256).digest()
    return base64.b32encode(raw[:_SIG_BYTES]).decode("ascii")


def parse_campaign_id(payload: str | None, *, master_salt: str | None = None) -> int:
    """Извлечь campaign_id из payload.

    Args:
        payload: строка после `/start `.
        master_salt: PSEUDONYM_MASTER_SALT для проверки HMAC-подписи.
            Если None — принимаем только legacy unsigned payload (для тестов).

    Returns:
        Целочисленный campaign_id.

    Raises:
        InvalidDeepLink: payload пустой / не подходит ни под один шаблон /
            HMAC-подпись не сходится.
    """
    if not payload:
        raise InvalidDeepLink("payload отсутствует")
    payload = payload.strip()

    # Новый формат: c<id>.<sig>.
    signed = _SIGNED_RE.match(payload)
    if signed is not None:
        if not master_salt:
            raise InvalidDeepLink("HMAC-подпись присутствует, но master_salt не задан")
        campaign_id = int(signed.group(1))
        expected = _sign(campaign_id, master_salt)
        provided = signed.group(2)
        if not hmac.compare_digest(expected, provided):
            raise InvalidDeepLink("HMAC-подпись deep-link некорректна")
        return campaign_id

    # Legacy unsigned (deprecation period).
    legacy = _LEGACY_RE.match(payload)
    if legacy is not None:
        logger.warning(
            "deprecated_unsigned_deeplink",
            extra={"payload": payload, "campaign_id": legacy.group(1)},
        )
        return int(legacy.group(1))

    raise InvalidDeepLink(f"payload не соответствует ни одному формату: {payload!r}")


def build_payload(campaign_id: int, *, master_salt: str | None = None) -> str:
    """Обратная функция для генерации invitation_url исследователем.

    Phase 5: если задан master_salt — выдаёт подписанный payload
    `c<id>.<sig>`. Иначе — legacy `c<id>` (для совместимости с тестами).
    """
    if campaign_id <= 0:
        raise ValueError("campaign_id должен быть положительным")
    if master_salt:
        return f"c{campaign_id}.{_sign(campaign_id, master_salt)}"
    return f"c{campaign_id}"
