"""Unit-тесты псевдонимизации респондентов (FR-DB-03, FR-RPT-05)."""

from __future__ import annotations

import hashlib

import pytest

from apps.api.reports.pseudonyms import session_to_pseudonym


def _hash(telegram_id: int, salt: bytes) -> bytes:
    """Воспроизводит логику apps.bot.services при регистрации сессии."""
    return hashlib.sha256(str(telegram_id).encode("utf-8") + salt).digest()


class TestSessionToPseudonym:
    def test_format_is_r_dash_four_digits(self) -> None:
        # Любой 32-байтовый SHA-256 даёт 4-значный псевдоним.
        h = hashlib.sha256(b"any").digest()
        result = session_to_pseudonym(h)
        assert result.startswith("R-")
        assert len(result) == 6
        assert result[2:].isdigit()

    def test_deterministic_per_hash(self) -> None:
        h = _hash(123456789, b"\xab" * 32)
        first = session_to_pseudonym(h)
        for _ in range(5):
            assert session_to_pseudonym(h) == first

    def test_same_telegram_id_different_campaign_salt_yields_different_pseudonym(
        self,
    ) -> None:
        # Главное FR-DB-03 свойство: тот же респондент в разных кампаниях
        # получает разные псевдонимы из-за per-campaign соли.
        salt_a = b"\x01" * 32
        salt_b = b"\x02" * 32
        h_a = _hash(987654321, salt_a)
        h_b = _hash(987654321, salt_b)
        # Хеши обязаны отличаться (per-campaign salt).
        assert h_a != h_b
        # Псевдонимы почти всегда отличаются; теоретическая коллизия 1/10000.
        # Берём пары salt-ов так, чтобы это свойство было видно на практике
        # — здесь конкретные salt_a/salt_b проверены вручную, не совпадает.
        assert session_to_pseudonym(h_a) != session_to_pseudonym(h_b)

    def test_rejects_too_short_hash(self) -> None:
        with pytest.raises(ValueError):
            session_to_pseudonym(b"\x00\x00\x00")  # 3 байта < 4

    def test_rejects_non_bytes(self) -> None:
        with pytest.raises(TypeError):
            session_to_pseudonym("not bytes")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            session_to_pseudonym(12345)  # type: ignore[arg-type]

    def test_accepts_bytes_like(self) -> None:
        h = hashlib.sha256(b"any").digest()
        from_bytearray = session_to_pseudonym(bytearray(h))
        from_memoryview = session_to_pseudonym(memoryview(h))
        from_bytes = session_to_pseudonym(h)
        assert from_bytes == from_bytearray == from_memoryview

    def test_pseudonym_space_well_distributed(self) -> None:
        # На 10 000 разных хешей псевдонимы покрывают значительную часть
        # 0000–9999 пространства (≈63% по теории шаров-урн).
        salt = b"\x00" * 32
        pseudonyms = {
            session_to_pseudonym(_hash(i, salt)) for i in range(10_000)
        }
        # Эмпирически ≈6300; даём запас от 5500 до 7100.
        assert 5500 <= len(pseudonyms) <= 7100
