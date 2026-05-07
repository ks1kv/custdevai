"""Абстрактные интерфейсы ML-модулей (NFR-MNT-03).

Конкретные реализации (RuBERTSentimentAnalyzer, BERTopicModeler) наследуют
эти интерфейсы. В тестах подменяются на Fake-реализации, что позволяет
проверять оркестрацию пайплайна без загрузки 1.5 ГБ весов моделей.
"""

from __future__ import annotations

import abc
from collections.abc import Sequence

from apps.ml.sentiment.schemas import SentimentInference
from apps.ml.topics.schemas import TopicModelingResult


class SentimentAnalyzer(abc.ABC):
    """Абстракция тонального классификатора (FR-SENT-01..08)."""

    @abc.abstractmethod
    def warmup(self) -> None:
        """Загрузить модель в память. Вызывается на старте Celery-worker
        для амортизации latency первого инференса (NFR-PRF-04)."""

    @abc.abstractmethod
    def analyze_batch(self, texts: Sequence[str], *, threshold: float) -> list[SentimentInference]:
        """Классифицировать батч ответов в три класса + low_confidence.

        Args:
            texts: список текстов ответов в порядке, важном для вызывающего.
            threshold: порог уверенности — при `max(softmax) < threshold`
                метка переключается на LOW_CONFIDENCE (FR-SENT-05).

        Returns:
            Список SentimentInference той же длины, что texts. Не-русские
            тексты помечаются `is_language_error=True` (FR-SENT-06) и
            не подсчитываются в агрегированной статистике вызывающим.
        """


class TopicModeler(abc.ABC):
    """Абстракция тематического моделирования (FR-TOP-01..08)."""

    @abc.abstractmethod
    def warmup(self) -> None:
        """Загрузить sentence-transformer и подготовить BERTopic-pipeline."""

    @abc.abstractmethod
    def fit_transform(
        self,
        texts: Sequence[str],
        *,
        session_ids: Sequence[int],
        target_topic_count: int,
    ) -> TopicModelingResult:
        """Кластеризовать ответы по темам.

        Args:
            texts: тексты ответов.
            session_ids: id сессий, параллельный массив той же длины
                (используется для построения SessionTopicAssignment).
            target_topic_count: целевое число тем в [3, 20] (FR-TOP-04).

        Returns:
            TopicModelingResult с темами (включая «прочее» — FR-TOP-06)
            и поассоциациями session→topic.
        """
