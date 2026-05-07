"""Эвристический детектор русского языка (FR-SENT-06).

Подтверждённое решение Phase 3: эвристика по доле кириллических символов.
Никаких новых зависимостей (langdetect / fasttext-langid отвергнуты).
"""

from __future__ import annotations

# Минимальная доля кириллицы (по отношению к буквенным символам), при
# которой текст считается русским. На коротких ответах вроде "ок" /
# "yes" эвристика мягкая: пустая строка → не-русский, но дальше пайплайн
# отфильтрует low_confidence.
_MIN_CYRILLIC_RATIO = 0.5


def is_russian_text(text: str) -> bool:
    """Вернуть True, если доля кириллических букв ≥ 50% от всех букв.

    Эмодзи, цифры, пунктуация и пробелы не учитываются ни в числителе,
    ни в знаменателе — это даёт стабильность на ответах вроде «👍 нет!».
    """
    if not text:
        return False
    cyrillic = 0
    letters = 0
    for ch in text:
        if ch.isalpha():
            letters += 1
            if "Ѐ" <= ch <= "ӿ":
                cyrillic += 1
    if letters == 0:
        return False
    return (cyrillic / letters) >= _MIN_CYRILLIC_RATIO
