"""RuBERT-based тональный анализатор (FR-SENT-01..08).

Используется DeepPavlov/rubert-base-cased по умолчанию (см. §1.4.3 теор.
главы). Модель и tokenizer загружаются лениво при первом обращении или
явно через warmup() при старте Celery-worker.

Классификация в 3 класса позитивный/нейтральный/негативный с порогом
уверенности (FR-SENT-05): ниже порога метка переключается на
LOW_CONFIDENCE и ответ исключается из агрегированной статистики.

Для Phase 3 baseline — zero-shot через мультиклассовую softmax-голову
существующей модели DeepPavlov/rubert-base-cased. Fine-tune на
RuSentNE-2023 для production-deploy — задача Phase 5 (training-pipeline).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from apps.api.config import Settings
from apps.api.db.models import SentimentLabel
from apps.ml.base import SentimentAnalyzer
from apps.ml.language import is_russian_text
from apps.ml.seeds import set_global_seeds
from apps.ml.sentiment.schemas import SentimentInference

logger = logging.getLogger(__name__)

# Маппинг id класса в модели → SentimentLabel. Для baseline-режима без
# fine-tune предполагается стандартное упорядочение классов RuBERT, которое
# фиксируется при первой загрузке через id2label config модели.
_DEFAULT_LABEL_MAP: dict[str, SentimentLabel] = {
    "positive": SentimentLabel.POSITIVE,
    "позитивный": SentimentLabel.POSITIVE,
    "neutral": SentimentLabel.NEUTRAL,
    "нейтральный": SentimentLabel.NEUTRAL,
    "negative": SentimentLabel.NEGATIVE,
    "негативный": SentimentLabel.NEGATIVE,
    "label_0": SentimentLabel.NEGATIVE,  # стандарт DeepPavlov-fine-tune
    "label_1": SentimentLabel.NEUTRAL,
    "label_2": SentimentLabel.POSITIVE,
}


class RuBERTSentimentAnalyzer(SentimentAnalyzer):
    """Конкретная реализация SentimentAnalyzer на transformers.

    Тяжёлые зависимости (torch, transformers) импортируются лениво при
    warmup() — это позволяет импортировать класс из api-контейнера без
    .[ml] extras (например, для тайпчекинга и регистрации DI).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._torch: Any | None = None

    def warmup(self) -> None:
        """Загрузить tokenizer и модель в память (NFR-PRF-04)."""
        if self._model is not None:
            return
        try:
            import torch  # type: ignore[import-untyped]
            from transformers import (  # type: ignore[import-untyped]
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except ImportError as exc:  # pragma: no cover — без ".[ml]" не вызывается
            raise RuntimeError("Тональный анализ требует extras: pip install -e '.[ml]'") from exc

        set_global_seeds(self._settings.sentiment_random_seed)
        cache_dir = self._settings.ml_model_cache_dir or None
        self._tokenizer = AutoTokenizer.from_pretrained(
            self._settings.sentiment_model_name, cache_dir=cache_dir
        )
        self._model = AutoModelForSequenceClassification.from_pretrained(
            self._settings.sentiment_model_name, cache_dir=cache_dir
        )
        self._model.eval()
        self._torch = torch
        logger.info(
            "rubert_warmup_complete",
            extra={
                "model_name": self._settings.sentiment_model_name,
                "num_labels": getattr(self._model.config, "num_labels", None),
            },
        )

    def analyze_batch(self, texts: Sequence[str], *, threshold: float) -> list[SentimentInference]:
        if not texts:
            return []
        self.warmup()
        assert self._model is not None
        assert self._tokenizer is not None
        assert self._torch is not None
        torch = self._torch

        inferences: list[SentimentInference] = []
        batch_size = self._settings.sentiment_batch_size

        # FR-SENT-06: не-русские тексты пропускаются до модели.
        for start in range(0, len(texts), batch_size):
            chunk = texts[start : start + batch_size]
            mask_russian = [is_russian_text(t) for t in chunk]
            chunk_ru = [t for t, ok in zip(chunk, mask_russian, strict=True) if ok]

            if chunk_ru:
                tokens = self._tokenizer(
                    chunk_ru,
                    return_tensors="pt",
                    truncation=True,
                    padding=True,
                    max_length=512,
                )
                with torch.no_grad():
                    logits = self._model(**tokens).logits
                probs = torch.softmax(logits, dim=-1)
                confidences, predicted = torch.max(probs, dim=-1)
                ru_results = list(zip(predicted.tolist(), confidences.tolist(), strict=True))
            else:
                ru_results = []

            ru_idx = 0
            for is_ru in mask_russian:
                if not is_ru:
                    inferences.append(
                        SentimentInference(
                            label=SentimentLabel.LOW_CONFIDENCE,
                            confidence=0.0,
                            is_language_error=True,
                        )
                    )
                    continue
                pred_id, conf = ru_results[ru_idx]
                ru_idx += 1
                label = self._map_label(pred_id)
                if conf < threshold:
                    label = SentimentLabel.LOW_CONFIDENCE
                inferences.append(SentimentInference(label=label, confidence=float(conf)))

        return inferences

    def _map_label(self, predicted_id: int) -> SentimentLabel:
        assert self._model is not None
        id2label: dict[int, str] = getattr(self._model.config, "id2label", {})
        raw = id2label.get(predicted_id, f"label_{predicted_id}")
        normalized = str(raw).lower().strip()
        return _DEFAULT_LABEL_MAP.get(normalized, SentimentLabel.LOW_CONFIDENCE)
