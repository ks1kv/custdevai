"""NFR-PRF-04 — ML-анализ кампании 200 сессий за ≤ 10 минут.

Seed-ит синтетическую кампанию с N сессиями по 5 ответов, потом запускает
`analyze_campaign(campaign_id)` в eager-режиме Celery и замеряет
wall-time от старта до `analysis_status=completed`.

Требует установленных `.[ml]` extras (transformers, torch, bertopic).
Реалистичный замер делается на Selectel-стенде после деплоя; локально
без GPU прогон может занимать существенно больше 10 минут — это
ожидаемо для baseline-CPU без ускорителей.

CLI:
    CELERY_TASK_ALWAYS_EAGER=true \\
        python -m tests.load.scenario_2_ml_analyze --sessions 200

Печатает JSON-сводку: {sessions, wall_time_s, target_s, passed}.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass

from tests.load._helpers import make_session_factory, run, seed_campaign_with_sessions

logger = logging.getLogger(__name__)


@dataclass
class Scenario2Result:
    sessions: int
    wall_time_s: float
    target_s: float
    passed: bool


async def _seed_and_analyze(session_count: int) -> Scenario2Result:
    engine, factory = make_session_factory()
    try:
        async with factory() as db:
            seed = await seed_campaign_with_sessions(session_count=session_count, db=db)
        campaign_id = seed["campaign_id"]
    finally:
        await engine.dispose()

    # Импорт ml_pipeline отложен: при eager-режиме `.delay()` синхронно
    # пройдёт весь анализ в текущем процессе. Это даёт честный wall-time
    # замер без сетевых издержек Celery worker.
    from apps.worker.tasks.ml_pipeline import analyze_campaign

    start = time.perf_counter()
    analyze_campaign.delay(campaign_id)
    elapsed = time.perf_counter() - start

    target = 600.0  # NFR-PRF-04: 10 минут
    return Scenario2Result(
        sessions=session_count,
        wall_time_s=elapsed,
        target_s=target,
        passed=elapsed <= target,
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="NFR-PRF-04 ML-нагрузка")
    parser.add_argument("--sessions", type=int, default=200)
    args = parser.parse_args()

    result = run(_seed_and_analyze(args.sessions))
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
