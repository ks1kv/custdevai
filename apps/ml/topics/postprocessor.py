"""Подбор репрезентативных цитат для каждой темы (FR-TOP-03).

Для каждой темы выбираем top-3 ответа, ближайшие к centroid эмбеддингов
кластера. Их тексты попадают в SessionTopicAssignment.representative_quote.

Используется numpy для cosine-distance — он уже есть в зависимостях
sentence-transformers / sklearn и не требует дополнительных пакетов.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def select_representative_indices(
    embeddings: Any,
    topic_assignments: Sequence[int],
    *,
    top_k: int = 3,
) -> dict[int, list[int]]:
    """Для каждой не-шумовой темы вернуть индексы top_k ближайших к centroid.

    Args:
        embeddings: numpy.ndarray формы (N, D) — эмбеддинги ответов.
        topic_assignments: список длины N с topic_id для каждого ответа;
            -1 означает шумовой кластер HDBSCAN (FR-TOP-06).
        top_k: сколько ближайших ответов взять (default 3, FR-TOP-03).

    Returns:
        dict {topic_id → [индексы N в порядке возрастания расстояния]}.
        Шумовая тема (-1) пропускается.
    """
    import numpy as np  # type: ignore[import-untyped]

    by_topic: dict[int, list[int]] = {}
    for idx, t in enumerate(topic_assignments):
        if t == -1:
            continue
        by_topic.setdefault(t, []).append(idx)

    result: dict[int, list[int]] = {}
    for topic_id, indices in by_topic.items():
        cluster = np.asarray(embeddings)[indices]
        centroid = cluster.mean(axis=0, keepdims=True)
        # Cosine distance: 1 - cosine_similarity. Чем меньше — тем ближе.
        norms_cluster = np.linalg.norm(cluster, axis=1, keepdims=True) + 1e-12
        norm_centroid = np.linalg.norm(centroid, axis=1, keepdims=True) + 1e-12
        sims = (cluster @ centroid.T) / (norms_cluster * norm_centroid)
        distances = 1.0 - sims.flatten()
        order = np.argsort(distances)
        chosen = [indices[i] for i in order[:top_k]]
        result[topic_id] = chosen
    return result
