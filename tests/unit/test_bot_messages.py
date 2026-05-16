"""Unit-тесты шаблонов сообщений бота: рендер без ошибок, кириллица."""

from __future__ import annotations

from apps.bot import messages


def _is_russian(s: str) -> bool:
    return any("Ѐ" <= ch <= "ӿ" for ch in s)


def test_static_messages_are_russian() -> None:
    for name in (
        "CONSENT_REQUIRED_REMINDER",
        "INVALID_DEEPLINK",
        "CAMPAIGN_NOT_RUNNING",
        "ALREADY_COMPLETED",
        "ANSWER_ACCEPTED_SHORT",
        "ANSWER_TOO_LONG",
        "LONG_ANSWER_CHUNK_ACCEPTED",
        "NON_TEXT_REJECTED",
        "INTERRUPTED_MESSAGE",
        "COMPLETED_MESSAGE",
        "INTERNAL_ERROR",
        "CAMPAIGN_PAUSED_REJECT",
        "CAMPAIGN_COMPLETED_REJECT",
        "NON_CYRILLIC_REJECTED",
        "QUESTION_SKIPPED_ACCEPTED",
        "QUESTION_REQUIRED_REJECT",
        "SKIP_OUTSIDE_INTERVIEW",
    ):
        msg = getattr(messages, name)
        assert isinstance(msg, str)
        assert _is_russian(msg), f"{name} doesn't contain Cyrillic"


def test_has_cyrillic_helper() -> None:
    """FR-SENT-06: бот отбраковывает ответы без кириллицы."""
    from apps.bot.handlers.interview import _has_cyrillic

    # Должны проходить
    assert _has_cyrillic("привет")
    assert _has_cyrillic("Купил latte в Старбакс")  # смешанный текст ок
    assert _has_cyrillic("А")
    assert _has_cyrillic("ё")
    # Не должны проходить
    assert not _has_cyrillic("a esli vot tak, shavaesh?")
    assert not _has_cyrillic("")
    assert not _has_cyrillic("123 !@#")
    assert not _has_cyrillic("😀👍")
    assert not _has_cyrillic("Hello, world")


def test_consent_text_renders() -> None:
    text = messages.CONSENT_TEXT.format(campaign_title="Тестовая кампания")
    assert "Тестовая кампания" in text
    assert _is_russian(text)


def test_question_template_renders() -> None:
    text = messages.QUESTION_TEMPLATE.format(idx=1, total=3, text="Сколько вам лет?")
    assert "Вопрос 1 из 3" in text
    assert "Сколько вам лет?" in text


def test_researcher_notify_renders() -> None:
    text = messages.RESEARCHER_NOTIFY_ALL_SESSIONS_COMPLETED.format(
        campaign_title="X", campaign_id=7, completed_count=10, interrupted_count=2
    )
    assert "X" in text and "7" in text and "10" in text and "2" in text
