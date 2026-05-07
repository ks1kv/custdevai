"""Unit-тест выбора top-3 цитат по близости к centroid (FR-TOP-03)."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from apps.ml.topics.postprocessor import select_representative_indices  # noqa: E402


def test_selects_top3_closest_to_centroid() -> None:
    # Кластер 0: 3D-точки с разным угловым отклонением. 0..2 — у direction
    # (1, 0.05, 0.05); 3..4 — отклонены к (0.5, 1, 0) и (0.5, 0, 1).
    embeddings = np.array(
        [
            [1.0, 0.05, 0.0],
            [1.0, 0.0, 0.05],
            [1.0, 0.05, 0.05],
            [0.5, 1.0, 0.0],
            [0.5, 0.0, 1.0],
            [0.0, 0.0, 1.0],  # кластер 1
            [0.05, 0.0, 1.0],
            [0.0, 0.05, 1.0],
        ],
        dtype=float,
    )
    assignments = [0, 0, 0, 0, 0, 1, 1, 1]

    result = select_representative_indices(embeddings, assignments, top_k=3)
    # Ближайшие 3 к centroid кластера 0 — индексы из {0, 1, 2}.
    assert set(result[0]).issubset({0, 1, 2})
    assert len(result[0]) == 3
    assert len(result[1]) == 3


def test_skips_noise_topic() -> None:
    embeddings = np.array([[1.0], [1.1], [2.0]])
    assignments = [-1, -1, -1]
    assert select_representative_indices(embeddings, assignments, top_k=3) == {}


def test_smaller_cluster_returns_full_size() -> None:
    embeddings = np.array([[1.0, 0.0], [1.0, 0.1]])
    assignments = [0, 0]
    result = select_representative_indices(embeddings, assignments, top_k=3)
    assert sorted(result[0]) == [0, 1]
