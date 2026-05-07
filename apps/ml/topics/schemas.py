"""DTO результатов тематического моделирования (FR-TOP-08)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TopicResult:
    """Описание одной темы (FR-TOP-02, FR-TOP-05, FR-TOP-06).

    topic_id_in_model: id темы в BERTopic (-1 → шум HDBSCAN, FR-TOP-06).
    label: опциональная человекочитаемая метка (None для baseline,
        генерируется LLM-summarizer-ом в Phase 5).
    keywords: 5-10 наиболее характерных слов по c-TF-IDF (FR-TOP-02).
    frequency_count: число ответов, отнесённых к теме (FR-TOP-05).
    is_noise: True, если HDBSCAN не отнёс ответы к ни одному кластеру.
    representative_quotes: top-3 цитаты, ближайшие к centroid (FR-TOP-03).
    """

    topic_id_in_model: int
    keywords: list[str]
    frequency_count: int
    is_noise: bool = False
    label: str | None = None
    representative_quotes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SessionTopicAssignment:
    """Привязка одной сессии к одной теме."""

    session_id: int
    topic_id_in_model: int
    representative_quote: str | None = None


@dataclass(frozen=True)
class TopicModelingResult:
    """Полный результат BERTopic.fit_transform (FR-TOP-08).

    topics — упорядоченный список найденных тем.
    assignments — какому ответу (по session_id) какая тема назначена.
        Ответы из шумового кластера попадают сюда с topic_id_in_model=-1.
    """

    topics: list[TopicResult]
    assignments: list[SessionTopicAssignment]
