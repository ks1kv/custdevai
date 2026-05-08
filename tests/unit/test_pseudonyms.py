"""Unit-тесты псевдонимизации респондентов (FR-DB-03, FR-RPT-05)."""

from __future__ import annotations

import pytest

from apps.api.reports.pseudonyms import session_to_pseudonym


class TestSessionToPseudonym:
    def test_format_is_r_dash_four_digits(self) -> None:
        assert session_to_pseudonym(1) == "R-0001"
        assert session_to_pseudonym(42) == "R-0042"
        assert session_to_pseudonym(9999) == "R-9999"

    def test_wraparound_modulo_10000(self) -> None:
        # session.id=10000 переходит в R-0000 — допустимо для MVP (Q1).
        assert session_to_pseudonym(10000) == "R-0000"
        assert session_to_pseudonym(10042) == "R-0042"
        assert session_to_pseudonym(99999) == "R-9999"

    def test_telegram_id_never_used(self) -> None:
        # Псевдоним зависит ТОЛЬКО от session.id (FR-BOT-10),
        # никогда не от telegram_id. session_id=1 всегда даёт R-0001.
        for _ in range(5):
            assert session_to_pseudonym(1) == "R-0001"

    @pytest.mark.parametrize("invalid", [0, -1, -9999])
    def test_rejects_non_positive(self, invalid: int) -> None:
        with pytest.raises(ValueError):
            session_to_pseudonym(invalid)

    def test_no_collision_within_campaign(self) -> None:
        # Внутри одной кампании session.id уникален и < 10000 на MVP-нагрузке —
        # коллизий быть не должно.
        seen = {session_to_pseudonym(i) for i in range(1, 10000)}
        assert len(seen) == 9999
