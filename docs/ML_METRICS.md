# Метрики качества тонального анализа CustDevAI (FR-SENT-07)

Документ фиксирует фактические показатели качества модуля анализа
тональности после fine-tune RuBERT-классификатора на русскоязычной
выборке RuSentNE-2023.

## Цели приёмки

| Требование | Целевое значение | Источник |
|---|---|---|
| FR-SENT-07 accuracy | ≥ 0.75 на ≥ 200 размеченных русскоязычных текстах | docs/03_requirements_specification.md |
| FR-SENT-07 weighted F1 | ≥ 0.73 | docs/03_requirements_specification.md |
| FR-SENT-04 воспроизводимость | побитово равные SentimentInference при одном seed | docs/03_requirements_specification.md |

## Воспроизведение

Полный пайплайн обучения реализован в `apps/ml/sentiment/training.py`.
Запуск:

```bash
docker compose exec worker python -m apps.ml.sentiment.training \
    --output /models/rubert-finetuned \
    --epochs 3 --batch-size 8 --lr 2e-5 --seed 42
```

Параметры подобраны под CPU-runner Selectel-инстанса. На GPU-машине
можно увеличить `--batch-size 16` и `--epochs 5`.

После завершения:

1. Веса (model + tokenizer) сохраняются в `--output`.
2. Контрольная выборка ≥ 200 примеров — в
   `tests/ml/data/rusentne_2023_holdout.json` (stratified split,
   seed=42, не пересекается с обучающей выборкой).
3. Метрики — в `<output>/metrics.json`.

Чтобы новые веса использовались бэкендом, переменная окружения:

```env
SENTIMENT_MODEL_PATH=/models/rubert-finetuned
```

## Фактические результаты

> **Заполняется после успешного fine-tune.** Если в production-окружении
> метрики ниже целевых, в этом разделе фиксируется причина и план
> устранения (см. также `train_subsample`, `weight_decay`, `epochs` в
> `TrainingConfig`).

### Конфигурация прогона

| Параметр | Значение |
|---|---|
| Модель базовая | `DeepPavlov/rubert-base-cased` |
| Датасет | RuSentNE-2023 / `MonoHime/ru_sentiment_dataset` |
| Размер обучающей выборки | _TBD_ |
| Размер контрольной выборки (holdout) | _TBD (≥ 200, FR-SENT-07)_ |
| Распределение классов train (pos/neu/neg) | _TBD_ |
| Epochs | 3 |
| Batch size | 8 |
| Learning rate | 2e-5 |
| Weight decay | 0.01 |
| Warmup steps | 100 |
| Max sequence length | 256 |
| Seed | 42 |
| Hardware | _TBD_ |
| Длительность обучения | _TBD_ |

### Финальные метрики на holdout

| Метрика | Значение | Цель FR-SENT-07 | Статус |
|---|---|---|---|
| Accuracy | _TBD_ | ≥ 0.75 | _TBD_ |
| Weighted F1 | _TBD_ | ≥ 0.73 | _TBD_ |
| Macro F1 | _TBD_ | — (наблюдение) | — |

### Per-class precision/recall/F1

| Класс | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| positive | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| neutral | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| negative | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### Confusion matrix

|  | pred neg | pred neu | pred pos |
|---|---|---|---|
| actual neg | _TBD_ | _TBD_ | _TBD_ |
| actual neu | _TBD_ | _TBD_ | _TBD_ |
| actual pos | _TBD_ | _TBD_ | _TBD_ |

### Сравнение с baseline (RuBERT без fine-tune)

| Метрика | Baseline (zero-shot) | После fine-tune | Δ |
|---|---|---|---|
| Accuracy | _TBD_ | _TBD_ | _TBD_ |
| Weighted F1 | _TBD_ | _TBD_ | _TBD_ |

## Воспроизводимость (FR-SENT-04)

Два прогона training с одним seed=42 дают побитово идентичный holdout
и идентичные веса. Это проверяется через приёмочный тест
`tests/ml/test_sentiment_quality.py::test_sentiment_reproducibility`
(требует `pytest -m ml` и установленных `.[ml]` extras).

## Принятие приёмки

Жёсткие assert FR-SENT-07 (`accuracy ≥ 0.75`, `weighted F1 ≥ 0.73`)
включаются переменной окружения `SENTIMENT_ASSERT_FR_07=true`:

```bash
SENTIMENT_MODEL_PATH=/models/rubert-finetuned \
SENTIMENT_ASSERT_FR_07=true \
    pytest -m ml tests/ml/test_sentiment_quality.py -v
```

Зелёный прогон этой команды на момент защиты ВКР означает, что
FR-SENT-07 закрыто полностью.

## Если цели не достигнуты на первом прогоне

Стратегия итераций (по решению пользователя, Phase 5 plan Q2):

1. **Прогон 1 (baseline-параметры):** lr=2e-5, epochs=3, batch=8.
2. **Прогон 2:** lr=3e-5 либо 1e-5, epochs=4, balance via class weights.
3. **Прогон 3:** более длинная max_length 384, gradient accumulation.

После 3-го прогона фиксируется фактический результат **без подгонки
тестовой выборки**. При расхождении с FR-SENT-07 в этом документе
явно указывается gap и план Phase 6.
