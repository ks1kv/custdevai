"""BERTopic-модель тематического моделирования (FR-TOP-01..08).

Стек (см. §1.4.4–1.4.5 теор. главы):
  * intfloat/multilingual-e5-base — sentence-transformer эмбеддер;
  * UMAP n_components=5, n_neighbors=15, cosine — снижение размерности;
  * HDBSCAN — плотностная кластеризация без предзаданного K (FR-TOP-06);
  * c-TF-IDF — 5–10 ключевых слов на тему (FR-TOP-02).

После fit_transform вызывается reduce_topics(nr_topics=target_topic_count)
для FR-TOP-04 (default 10, диапазон 3..20).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from apps.api.config import Settings
from apps.ml.base import TopicModeler
from apps.ml.seeds import set_global_seeds
from apps.ml.topics.postprocessor import select_representative_indices
from apps.ml.topics.schemas import (
    SessionTopicAssignment,
    TopicModelingResult,
    TopicResult,
)

logger = logging.getLogger(__name__)


class BERTopicModeler(TopicModeler):
    """BERTopic-реализация TopicModeler."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._embedder: Any | None = None
        self._bertopic_factory: Any | None = None
        self._umap_factory: Any | None = None
        self._hdbscan_factory: Any | None = None

    def warmup(self) -> None:
        if self._embedder is not None:
            return
        try:
            from bertopic import BERTopic  # type: ignore[import-untyped]
            from hdbscan import HDBSCAN  # type: ignore[import-untyped]
            from sentence_transformers import (  # type: ignore[import-untyped]
                SentenceTransformer,
            )
            from umap import UMAP  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Тематическое моделирование требует extras: pip install -e '.[ml]'"
            ) from exc

        set_global_seeds(self._settings.topic_random_seed)
        self._embedder = SentenceTransformer(
            self._settings.topic_embedder_name,
            cache_folder=self._settings.ml_model_cache_dir or None,
        )
        self._bertopic_factory = BERTopic
        self._umap_factory = UMAP
        self._hdbscan_factory = HDBSCAN
        logger.info(
            "bertopic_warmup_complete",
            extra={"embedder": self._settings.topic_embedder_name},
        )

    def fit_transform(
        self,
        texts: Sequence[str],
        *,
        session_ids: Sequence[int],
        target_topic_count: int,
    ) -> TopicModelingResult:
        if not texts:
            return TopicModelingResult(topics=[], assignments=[])
        if len(texts) != len(session_ids):
            raise ValueError("texts и session_ids должны быть параллельны")

        self.warmup()
        assert self._embedder is not None
        assert self._bertopic_factory is not None
        assert self._umap_factory is not None
        assert self._hdbscan_factory is not None
        BERTopic = self._bertopic_factory  # noqa: N806
        UMAP = self._umap_factory  # noqa: N806
        HDBSCAN = self._hdbscan_factory  # noqa: N806

        embeddings = self._embedder.encode(
            list(texts), show_progress_bar=False, convert_to_numpy=True
        )

        # min_cluster_size — эвристика: ≥2, не больше 1/20 корпуса.
        # Финальный тюнинг на нагрузочных данных — Phase 5.
        min_cluster_size = max(2, len(texts) // 20)
        umap_model = UMAP(
            n_neighbors=15,
            n_components=5,
            metric="cosine",
            random_state=self._settings.topic_random_seed,
        )
        hdbscan_model = HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric="euclidean",
            prediction_data=True,
        )

        topic_model = BERTopic(
            embedding_model=self._embedder,
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            calculate_probabilities=False,
            verbose=False,
        )
        topic_assignments_raw, _ = topic_model.fit_transform(
            list(texts), embeddings=embeddings
        )
        topic_assignments: list[int] = [int(t) for t in topic_assignments_raw]

        # Сжатие до целевого числа тем (FR-TOP-04).
        try:
            topic_model.reduce_topics(list(texts), nr_topics=target_topic_count)
            topic_assignments = [int(t) for t in topic_model.topics_]
        except Exception:  # pragma: no cover  — на коротких корпусах reduce_topics
            # может не сработать; оставляем исходный набор тем.
            logger.warning("reduce_topics failed, keeping original topics")

        # Top-3 представителя на каждую тему (FR-TOP-03).
        representative_idx = select_representative_indices(
            embeddings, topic_assignments, top_k=3
        )

        # Сборка TopicResult-ов.
        topic_info = topic_model.get_topic_info()
        topics: list[TopicResult] = []
        for _, row in topic_info.iterrows():
            t_id = int(row["Topic"])
            count = int(row["Count"])
            keywords_pairs = topic_model.get_topic(t_id) or []
            keywords = [str(w) for w, _ in keywords_pairs[:10]]
            quotes_idx = representative_idx.get(t_id, [])
            quotes = [texts[i] for i in quotes_idx]
            topics.append(
                TopicResult(
                    topic_id_in_model=t_id,
                    keywords=keywords,
                    frequency_count=count,
                    is_noise=(t_id == -1),
                    label=None,
                    representative_quotes=quotes,
                )
            )

        assignments: list[SessionTopicAssignment] = []
        # Для top-3 индексов помечаем representative_quote (текст ответа),
        # для остальных — None (FR-TOP-03 + sparse-storage по Q2 решению).
        rep_set = {idx for idxs in representative_idx.values() for idx in idxs}
        for i, sid in enumerate(session_ids):
            tid = topic_assignments[i] if i < len(topic_assignments) else -1
            quote = texts[i] if i in rep_set else None
            assignments.append(
                SessionTopicAssignment(
                    session_id=sid,
                    topic_id_in_model=tid,
                    representative_quote=quote,
                )
            )

        return TopicModelingResult(topics=topics, assignments=assignments)
