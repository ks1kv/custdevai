"""Unit-тесты set_global_seeds (FR-SENT-04, FR-TOP-07, NFR-COR-01)."""

from __future__ import annotations

import os
import random

from apps.ml.seeds import set_global_seeds


def test_random_module_seed_fixed() -> None:
    set_global_seeds(42)
    a = [random.random() for _ in range(5)]
    set_global_seeds(42)
    b = [random.random() for _ in range(5)]
    assert a == b


def test_pythonhashseed_set() -> None:
    set_global_seeds(123)
    assert os.environ["PYTHONHASHSEED"] == "123"


def test_different_seeds_yield_different_streams() -> None:
    set_global_seeds(1)
    a = random.random()
    set_global_seeds(2)
    b = random.random()
    assert a != b


def test_numpy_seed_optional() -> None:
    """Если numpy установлен, его state должен совпадать после set_global_seeds."""
    np = None
    try:
        import numpy as np  # type: ignore[import-untyped]
    except ImportError:
        return
    set_global_seeds(7)
    a = np.random.rand(3).tolist()
    set_global_seeds(7)
    b = np.random.rand(3).tolist()
    assert a == b
