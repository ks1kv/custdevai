"""Глобальная фиксация seed-значений для воспроизводимости (FR-SENT-04, FR-TOP-07, NFR-COR-01).

`set_global_seeds(seed)` инициализирует генераторы случайных чисел всех
библиотек, которые могут быть задействованы в ML-инференсе:

  - встроенный `random` (для сценариев, где Python random затрагивает
    препроцессинг);
  - `numpy.random` (UMAP, HDBSCAN, sklearn используют его);
  - `torch` CPU и CUDA (transformers/sentence-transformers);
  - `os.environ["PYTHONHASHSEED"]` (для детерминированных hash-операций
    словарей в numpy/UMAP).

torch и numpy импортируются лениво, чтобы модуль был импортируемым в
api-контейнере без ML-зависимостей (apps/api имеет setup без ".[ml]").
"""

from __future__ import annotations

import logging
import os
import random
from typing import Any

logger = logging.getLogger(__name__)


def set_global_seeds(seed: int) -> None:
    """Зафиксировать глобальные seed-значения для воспроизводимости пайплайна.

    Args:
        seed: целочисленное значение, которое логируется в structured-лог
            при каждом запуске пайплайна (см. apps/worker/tasks/ml_pipeline.py).
    """
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)

    # numpy и torch — только если установлены ([ml] extra).
    np = _try_import("numpy")
    if np is not None:
        np.random.seed(seed)

    torch = _try_import("torch")
    if torch is not None:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        # Детерминированный режим cuDNN — для FR-SENT-04 / NFR-COR-01.
        if hasattr(torch, "use_deterministic_algorithms"):
            try:
                torch.use_deterministic_algorithms(True, warn_only=True)
            except Exception:  # noqa: BLE001  — сред с CUDA-only ops пропускаем
                logger.debug("torch.use_deterministic_algorithms unavailable")

    logger.info("ml_seeds_set", extra={"seed": seed})


def _try_import(name: str) -> Any | None:
    try:
        return __import__(name)
    except ImportError:
        return None
