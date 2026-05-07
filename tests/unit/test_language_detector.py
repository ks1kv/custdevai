"""Unit-тесты эвристики is_russian_text (FR-SENT-06)."""

from __future__ import annotations

import pytest

from apps.ml.language import is_russian_text


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Это типичный русский ответ.", True),
        ("Привет!", True),
        ("Очень длинный текст с эмодзи 👍 и пунктуацией.", True),
        ("hello world", False),
        ("Mixed текст here", False),  # 5 cyr / 14 letters = 36% < 50%
        ("English with кириллица word", False),  # 9 cyr / 24 letters = 37.5% < 50%
        ("кириллица plus eng", True),  # 9 cyr / 16 letters = 56% ≥ 50%
        ("", False),
        ("12345", False),
        ("👍👍👍", False),  # буквы отсутствуют
        ("ok", False),
        ("ок", True),
    ],
)
def test_is_russian_text(text: str, expected: bool) -> None:
    assert is_russian_text(text) is expected
