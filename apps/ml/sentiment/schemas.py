"""DTO результатов тонального анализа."""

from __future__ import annotations

from dataclasses import dataclass

from apps.api.db.models import SentimentLabel


@dataclass(frozen=True)
class SentimentInference:
    """Результат классификации одного ответа.

    label: SentimentLabel (positive/neutral/negative/low_confidence).
    confidence: max softmax-вероятности класса в [0, 1] (FR-SENT-02).
    is_language_error: True, если текст не на русском (FR-SENT-06) — пайплайн
        пропустит запись в sentiment_results, чтобы не загрязнять статистику.
    """

    label: SentimentLabel
    confidence: float
    is_language_error: bool = False
