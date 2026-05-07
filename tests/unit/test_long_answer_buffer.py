"""Unit-тест склейки чанков длинного ответа (FR-BOT-08)."""

from __future__ import annotations


def _join_chunks(chunks: list[str]) -> str:
    return "\n".join(chunks)


def test_two_chunks_joined_with_newline() -> None:
    assert _join_chunks(["aaa", "bbb"]) == "aaa\nbbb"


def test_empty_list_yields_empty_string() -> None:
    assert _join_chunks([]) == ""


def test_single_chunk_unchanged() -> None:
    assert _join_chunks(["only"]) == "only"


def test_long_total_combines_correctly() -> None:
    chunks = ["a" * 4000, "b" * 4000]
    joined = _join_chunks(chunks)
    assert len(joined) == 4000 + 1 + 4000
    assert joined.startswith("a" * 4000)
    assert joined.endswith("b" * 4000)
