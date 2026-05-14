# RuSentNE-2023 holdout data

Этот каталог хранит контрольную выборку для FR-SENT-07 после успешного
прогона fine-tune через `python -m apps.ml.sentiment.training`:

```
rusentne_2023_holdout.json
```

Формат — JSON-массив объектов:

```json
[
  {"text": "Очень доволен сервисом", "label": "positive"},
  ...
]
```

Файл генерируется автоматически модулем `apps/ml/sentiment/training.py`
во время stratified split (фиксированный seed=42, не пересекается с
обучающей выборкой). Минимальный размер — 200 примеров (FR-SENT-07).

При запуске `pytest -m ml tests/ml/test_sentiment_quality.py` тест
загружает этот файл при наличии; иначе fallback на in-line примеры.

Жёсткий assert FR-SENT-07 (accuracy ≥ 0.75, weighted F1 ≥ 0.73) включается
переменной `SENTIMENT_ASSERT_FR_07=true`.
