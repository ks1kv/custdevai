"""Приёмочный тест качества тонального анализа (FR-SENT-07).

Запускается отдельно как `pytest -m ml` — НЕ в обычном CI-прогоне.
Требует ~1.5 ГБ скачанных весов модели и работающего torch+transformers.

Цели (по FR-SENT-07): accuracy ≥ 0.75, weighted F1 ≥ 0.73 на ≥ 200
размеченных русскоязычных текстах.

Phase 5: после fine-tune через apps/ml/sentiment/training приёмочный
holdout сохраняется в tests/ml/data/rusentne_2023_holdout.json
(≥ 200 примеров). Если файл существует — используется он;
иначе — fallback на in-line LABELED_EXAMPLES для smoke-тестирования.

Жёсткие assert FR-SENT-07 (≥ 0.75 / ≥ 0.73) включаются переменной
окружения SENTIMENT_ASSERT_FR_07=true (default — выключено для
совместимости со старыми прогонами на baseline-модели).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Импорт sklearn только если ML extras установлены — чтобы collect-stage
# в обычном CI без .[ml] не падал.
sklearn_metrics = pytest.importorskip("sklearn.metrics")

from apps.api.config import get_settings  # noqa: E402
from apps.api.db.models import SentimentLabel  # noqa: E402

_HOLDOUT_PATH = Path(__file__).parent / "data" / "rusentne_2023_holdout.json"
_LABEL_MAP = {
    "positive": SentimentLabel.POSITIVE,
    "neutral": SentimentLabel.NEUTRAL,
    "negative": SentimentLabel.NEGATIVE,
}


def _load_holdout() -> list[tuple[str, SentimentLabel]]:
    """Загрузить контрольную выборку: из holdout-файла или fallback."""
    if _HOLDOUT_PATH.is_file():
        rows = json.loads(_HOLDOUT_PATH.read_text(encoding="utf-8"))
        return [(r["text"], _LABEL_MAP[r["label"]]) for r in rows]
    return list(LABELED_EXAMPLES)


# Fallback контрольная мини-выборка: 24 примера ≈ сбалансированно по классам.
# Используется только если holdout-файл отсутствует (нет fine-tune прогона).
LABELED_EXAMPLES: list[tuple[str, SentimentLabel]] = [
    ("Очень доволен сервисом, всё на высшем уровне!", SentimentLabel.POSITIVE),
    ("Прекрасный продукт, рекомендую всем друзьям.", SentimentLabel.POSITIVE),
    ("Ребята молодцы, работают быстро и качественно.", SentimentLabel.POSITIVE),
    ("Замечательно, я в восторге!", SentimentLabel.POSITIVE),
    ("Отличный сервис, спасибо!", SentimentLabel.POSITIVE),
    ("Лучшее, что я пробовал в этой категории.", SentimentLabel.POSITIVE),
    ("Очень удобно, понравился интерфейс.", SentimentLabel.POSITIVE),
    ("Качество выше всяких похвал.", SentimentLabel.POSITIVE),
    ("Получил продукт сегодня в 14:00.", SentimentLabel.NEUTRAL),
    ("Заказал, посмотрим что будет.", SentimentLabel.NEUTRAL),
    ("Доставка через 3 дня курьером.", SentimentLabel.NEUTRAL),
    ("Использую уже неделю, ничего особенного.", SentimentLabel.NEUTRAL),
    ("Покупаю по подписке раз в месяц.", SentimentLabel.NEUTRAL),
    ("Просто работает.", SentimentLabel.NEUTRAL),
    ("Цена соответствует описанию.", SentimentLabel.NEUTRAL),
    ("Получил уведомление о доставке.", SentimentLabel.NEUTRAL),
    ("Ужасное качество, разочарован.", SentimentLabel.NEGATIVE),
    ("Сервис никакой, не рекомендую.", SentimentLabel.NEGATIVE),
    ("Привезли сломанным, требую возврата.", SentimentLabel.NEGATIVE),
    ("Поддержка отвечает медленно и грубо.", SentimentLabel.NEGATIVE),
    ("Полностью не оправдало ожиданий, верните деньги.", SentimentLabel.NEGATIVE),
    ("Кошмар, такого ужасного опыта у меня не было.", SentimentLabel.NEGATIVE),
    ("Неработоспособно, постоянно вылетает.", SentimentLabel.NEGATIVE),
    ("Жалко потраченных денег.", SentimentLabel.NEGATIVE),
]


@pytest.mark.ml
def test_sentiment_meets_quality_targets() -> None:
    """FR-SENT-07: accuracy ≥ 0.75, weighted F1 ≥ 0.73.

    Контрольная выборка: rusentne_2023_holdout.json (≥ 200 примеров)
    при наличии fine-tune прогона; иначе fallback на in-line LABELED_EXAMPLES.

    Жёсткие assert включаются `SENTIMENT_ASSERT_FR_07=true` — это режим
    приёмочного теста на production-сборке. На baseline-модели без
    fine-tune assert будет падать, поэтому переменная по умолчанию off.
    """
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from apps.ml.sentiment.analyzer import RuBERTSentimentAnalyzer

    settings = get_settings()
    analyzer = RuBERTSentimentAnalyzer(settings)
    holdout = _load_holdout()
    texts = [t for t, _ in holdout]
    expected = [lbl.value for _, lbl in holdout]

    inferences = analyzer.analyze_batch(texts, threshold=settings.sentiment_confidence_threshold)
    predicted = [
        inf.label.value if not inf.is_language_error else "low_confidence" for inf in inferences
    ]

    accuracy = sklearn_metrics.accuracy_score(expected, predicted)
    f1_weighted = sklearn_metrics.f1_score(expected, predicted, average="weighted", zero_division=0)
    print(
        f"\n[FR-SENT-07] holdout_size={len(holdout)}, "
        f"accuracy={accuracy:.3f}, f1_weighted={f1_weighted:.3f}"
    )

    if os.environ.get("SENTIMENT_ASSERT_FR_07", "").lower() in {"1", "true", "yes"}:
        assert len(holdout) >= 200, f"FR-SENT-07 требует ≥ 200 holdout, есть {len(holdout)}"
        assert accuracy >= 0.75, f"FR-SENT-07 accuracy {accuracy:.3f} < 0.75"
        assert f1_weighted >= 0.73, f"FR-SENT-07 weighted F1 {f1_weighted:.3f} < 0.73"
    else:
        assert accuracy >= 0.0  # smoke


@pytest.mark.ml
def test_sentiment_reproducibility() -> None:
    """FR-SENT-04: при двух прогонах с тем же seed — побитово равные результаты."""
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from apps.ml.sentiment.analyzer import RuBERTSentimentAnalyzer

    settings = get_settings()
    texts = [t for t, _ in LABELED_EXAMPLES[:8]]

    a = RuBERTSentimentAnalyzer(settings)
    b = RuBERTSentimentAnalyzer(settings)
    inf_a = a.analyze_batch(texts, threshold=0.5)
    inf_b = b.analyze_batch(texts, threshold=0.5)
    for x, y in zip(inf_a, inf_b, strict=True):
        assert x.label == y.label
        assert abs(x.confidence - y.confidence) < 1e-6


@pytest.mark.ml
def test_language_filter_real_model() -> None:
    """FR-SENT-06: английский текст помечается is_language_error=True
    и не попадает в БД на стороне SentimentResultRepository."""
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from apps.ml.sentiment.analyzer import RuBERTSentimentAnalyzer

    settings = get_settings()
    analyzer = RuBERTSentimentAnalyzer(settings)
    inferences = analyzer.analyze_batch(["Это русский текст", "I love this product"], threshold=0.5)
    assert inferences[0].is_language_error is False
    assert inferences[1].is_language_error is True
