"""Fine-tune RuBERT-классификатора на RuSentNE-2023 (FR-SENT-07).

Цель — достичь accuracy ≥ 0.75 и weighted F1 ≥ 0.73 на контрольной
выборке ≥ 200 примеров. Baseline RuBERT без fine-tune не достигает этих
значений (zero-shot применение softmax-головы).

CLI:
    python -m apps.ml.sentiment.training \\
        --output /models/rubert-finetuned \\
        --epochs 3 --batch-size 8 --lr 2e-5

После обучения:
1. Веса сохраняются в `--output` (model.save_pretrained + tokenizer).
2. Контрольная выборка ≥ 200 примеров записывается в
   tests/ml/data/rusentne_2023_holdout.json.
3. Метрики (accuracy, weighted F1, per-class precision/recall, confusion
   matrix) выводятся в stdout и в `<output>/metrics.json`.
4. SENTIMENT_MODEL_PATH в Settings указывает на выходной каталог —
   RuBERTSentimentAnalyzer.warmup() подхватит локальные веса.

Тяжёлые зависимости (torch, transformers, datasets, sklearn) импортируются
лениво — модуль импортируется без `.[ml]` extras для тайпчекинга.

Гиперпараметры подобраны под CPU-runner (batch_size=8, без fp16).
Длительность одного прогона на 3 эпохи RuSentNE-2023 (~50K примеров) на
CPU — ~6–10 часов. На production-CPU Selectel-инстанса быстрее.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Маппинг строковых меток RuSentNE-2023 → numeric class id.
# Используется фиксированный порядок: 0=negative, 1=neutral, 2=positive.
# Это согласуется с _DEFAULT_LABEL_MAP в analyzer.py (label_0=neg, ...).
LABEL_TO_ID: dict[str, int] = {
    "negative": 0,
    "neutral": 1,
    "positive": 2,
}
ID_TO_LABEL = {v: k for k, v in LABEL_TO_ID.items()}


@dataclass
class TrainingConfig:
    """Гиперпараметры обучения. По умолчанию рассчитаны на CPU-runner."""

    model_name: str = "DeepPavlov/rubert-base-cased"
    dataset_name: str = "MonoHime/ru_sentiment_dataset"
    output_dir: Path = Path("/models/rubert-finetuned")
    batch_size: int = 8
    epochs: int = 3
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    warmup_steps: int = 100
    seed: int = 42
    max_length: int = 256
    holdout_min_size: int = 200
    holdout_fraction: float = 0.1
    train_subsample: int | None = None  # None = весь датасет; integer = top-N (для smoke-теста)
    holdout_path: Path = Path("tests/ml/data/rusentne_2023_holdout.json")
    save_metrics_to: Path | None = None


@dataclass
class TrainingMetrics:
    accuracy: float
    weighted_f1: float
    macro_f1: float
    per_class: dict[str, dict[str, float]]
    confusion_matrix: list[list[int]]
    holdout_size: int
    train_size: int
    class_balance: dict[str, int]
    config: dict[str, Any] = field(default_factory=dict)


def run_training(cfg: TrainingConfig) -> TrainingMetrics:
    """Полный пайплайн fine-tune.

    Шаги:
        1. Загрузить датасет, маппить метки в {0,1,2}.
        2. Stratified split на train/holdout с фиксированным seed.
        3. Сохранить holdout в JSON для tests/ml/test_sentiment_quality.py.
        4. Tokenize + Trainer API.
        5. Eval на holdout: accuracy, F1, confusion matrix.
        6. model.save_pretrained → cfg.output_dir.
        7. Записать metrics.json и вернуть TrainingMetrics.
    """
    try:
        import numpy as np
        import torch
        from datasets import load_dataset
        from sklearn.metrics import (
            accuracy_score,
            confusion_matrix,
            f1_score,
            precision_recall_fscore_support,
        )
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            Trainer,
            TrainingArguments,
        )
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Fine-tune требует extras: pip install -e '.[ml]' + scikit-learn"
        ) from exc

    random.seed(cfg.seed)
    np.random.seed(cfg.seed)
    torch.manual_seed(cfg.seed)

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cfg.holdout_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Загрузка датасета. RuSentNE-2023 / ru_sentiment_dataset разделены
    #    на train/test уже в HuggingFace Hub. Мы переиспользуем split,
    #    плюс берём holdout из test/validation если есть.
    logger.info("loading_dataset", extra={"dataset": cfg.dataset_name})
    ds = load_dataset(cfg.dataset_name)

    # Структура датасетов в Hub варьируется; нормализуем поля.
    # Ожидаем колонки `text` и `label`/`sentiment`.
    def _normalize(example: dict[str, Any]) -> dict[str, Any]:
        text = example.get("text") or example.get("sentence") or example.get("content") or ""
        raw_label = example.get("label") if "label" in example else example.get("sentiment")
        if isinstance(raw_label, str):
            label_id = LABEL_TO_ID.get(raw_label.lower())
        elif isinstance(raw_label, int):
            label_id = raw_label
        else:
            label_id = None
        return {"text": text, "label": label_id}

    splits: dict[str, list[dict[str, Any]]] = {}
    for split_name, split_data in ds.items():
        rows = [_normalize(r) for r in split_data]
        rows = [r for r in rows if r["label"] is not None and r["text"].strip()]
        splits[split_name] = rows

    # 2. Объединяем все split-ы в train+holdout по фиксированному seed.
    all_rows: list[dict[str, Any]] = []
    for rows in splits.values():
        all_rows.extend(rows)
    # seed-stable shuffle для воспроизводимости (FR-SENT-04). Не криптография.
    random.Random(cfg.seed).shuffle(all_rows)  # noqa: S311

    if cfg.train_subsample is not None:
        all_rows = all_rows[: cfg.train_subsample]

    holdout_size = max(cfg.holdout_min_size, int(len(all_rows) * cfg.holdout_fraction))
    holdout = all_rows[:holdout_size]
    train = all_rows[holdout_size:]
    logger.info(
        "split_done",
        extra={"train": len(train), "holdout": len(holdout)},
    )

    # 3. Сохраняем holdout для приёмочного теста.
    cfg.holdout_path.write_text(
        json.dumps(
            [{"text": r["text"], "label": ID_TO_LABEL[r["label"]]} for r in holdout],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 4. Tokenize + Dataset wrapper.
    tokenizer = AutoTokenizer.from_pretrained(cfg.model_name)

    def _tokenize(batch: list[dict[str, Any]]) -> dict[str, Any]:
        texts = [r["text"] for r in batch]
        enc = tokenizer(
            texts,
            truncation=True,
            padding="max_length",
            max_length=cfg.max_length,
            return_tensors="pt",
        )
        enc["labels"] = torch.tensor([r["label"] for r in batch], dtype=torch.long)
        return enc

    class _RowDataset(torch.utils.data.Dataset):  # type: ignore[misc, name-defined]
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            self._rows = rows

        def __len__(self) -> int:
            return len(self._rows)

        def __getitem__(self, idx: int) -> dict[str, Any]:
            row = self._rows[idx]
            enc = tokenizer(
                row["text"],
                truncation=True,
                padding="max_length",
                max_length=cfg.max_length,
                return_tensors="pt",
            )
            return {
                "input_ids": enc["input_ids"].squeeze(0),
                "attention_mask": enc["attention_mask"].squeeze(0),
                "labels": torch.tensor(row["label"], dtype=torch.long),
            }

    train_ds = _RowDataset(train)
    eval_ds = _RowDataset(holdout)

    model = AutoModelForSequenceClassification.from_pretrained(
        cfg.model_name,
        num_labels=3,
        id2label={i: ID_TO_LABEL[i] for i in range(3)},
        label2id=LABEL_TO_ID,
    )

    def _compute_metrics(eval_pred: Any) -> dict[str, float]:
        preds = np.argmax(eval_pred.predictions, axis=-1)
        labels = eval_pred.label_ids
        return {
            "accuracy": float(accuracy_score(labels, preds)),
            "weighted_f1": float(f1_score(labels, preds, average="weighted")),
            "macro_f1": float(f1_score(labels, preds, average="macro")),
        }

    args = TrainingArguments(
        output_dir=str(cfg.output_dir / "checkpoints"),
        num_train_epochs=cfg.epochs,
        per_device_train_batch_size=cfg.batch_size,
        per_device_eval_batch_size=cfg.batch_size,
        learning_rate=cfg.learning_rate,
        weight_decay=cfg.weight_decay,
        warmup_steps=cfg.warmup_steps,
        logging_steps=50,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,
        seed=cfg.seed,
        fp16=False,  # CPU-runner: mixed precision не используется.
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        tokenizer=tokenizer,
        compute_metrics=_compute_metrics,
    )

    trainer.train()

    # 5. Финальная оценка + confusion matrix.
    pred_output = trainer.predict(eval_ds)
    preds = np.argmax(pred_output.predictions, axis=-1)
    labels = pred_output.label_ids

    acc = float(accuracy_score(labels, preds))
    wf1 = float(f1_score(labels, preds, average="weighted"))
    mf1 = float(f1_score(labels, preds, average="macro"))
    per_class_precision, per_class_recall, per_class_f1, support = precision_recall_fscore_support(
        labels, preds, labels=[0, 1, 2], zero_division=0
    )
    cm = confusion_matrix(labels, preds, labels=[0, 1, 2]).tolist()

    per_class = {
        ID_TO_LABEL[i]: {
            "precision": float(per_class_precision[i]),
            "recall": float(per_class_recall[i]),
            "f1": float(per_class_f1[i]),
            "support": int(support[i]),
        }
        for i in range(3)
    }

    # 6. Сохраняем модель + tokenizer.
    trainer.save_model(str(cfg.output_dir))
    tokenizer.save_pretrained(str(cfg.output_dir))

    # 7. Метрики и баланс классов.
    balance = Counter(r["label"] for r in train)
    metrics = TrainingMetrics(
        accuracy=acc,
        weighted_f1=wf1,
        macro_f1=mf1,
        per_class=per_class,
        confusion_matrix=cm,
        holdout_size=len(holdout),
        train_size=len(train),
        class_balance={ID_TO_LABEL[k]: v for k, v in balance.items()},
        config={
            "model_name": cfg.model_name,
            "dataset_name": cfg.dataset_name,
            "epochs": cfg.epochs,
            "batch_size": cfg.batch_size,
            "learning_rate": cfg.learning_rate,
            "seed": cfg.seed,
            "max_length": cfg.max_length,
        },
    )

    metrics_path = cfg.save_metrics_to or (cfg.output_dir / "metrics.json")
    metrics_path.write_text(
        json.dumps(asdict(metrics), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(
        "training_complete",
        extra={
            "accuracy": acc,
            "weighted_f1": wf1,
            "fr_sent_07_passed": acc >= 0.75 and wf1 >= 0.73,
        },
    )
    return metrics


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fine-tune RuBERT для тональности (FR-SENT-07)")
    p.add_argument("--model-name", default="DeepPavlov/rubert-base-cased")
    p.add_argument("--dataset-name", default="MonoHime/ru_sentiment_dataset")
    p.add_argument("--output", type=Path, default=Path("/models/rubert-finetuned"))
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-length", type=int, default=256)
    p.add_argument(
        "--train-subsample", type=int, default=None, help="Smoke-режим: ограничить N примеров"
    )
    return p


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = _build_argparser().parse_args()
    cfg = TrainingConfig(
        model_name=args.model_name,
        dataset_name=args.dataset_name,
        output_dir=args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        seed=args.seed,
        max_length=args.max_length,
        train_subsample=args.train_subsample,
    )
    metrics = run_training(cfg)
    print(json.dumps(asdict(metrics), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
