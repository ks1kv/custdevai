"""NFR-PRF-05 — генерация PDF/XLSX отчёта на 500 сессий за ≤ 30 секунд.

Seed-ит кампанию с 500 сессиями (5 ответов на каждую = 2500 answers),
помечает её analysis_status=COMPLETED (sentiment_results и topics не
обязательны — отчёт делает агрегаты по тем данным, что есть), и
вызывает ReportService.generate() с замером wall-time.

CLI:
    python -m tests.load.scenario_3_report_500 --sessions 500 --format pdf

Печатает JSON: {sessions, format, wall_time_s, target_s, passed, file_size}.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass

from apps.api.config import get_settings
from apps.api.db.models import ReportFormat
from apps.api.reports.service import ReportService
from tests.load._helpers import make_session_factory, run, seed_campaign_with_sessions

logger = logging.getLogger(__name__)


@dataclass
class Scenario3Result:
    sessions: int
    format: str
    wall_time_s: float
    target_s: float
    passed: bool
    file_size: int


async def _seed_and_generate(session_count: int, fmt: ReportFormat) -> Scenario3Result:
    engine, factory = make_session_factory()
    settings = get_settings()
    try:
        async with factory() as db:
            seed = await seed_campaign_with_sessions(session_count=session_count, db=db)
        campaign_id = seed["campaign_id"]

        async with factory() as db:
            service = ReportService(session=db, settings=settings)
            start = time.perf_counter()
            report = await service.generate(campaign_id, fmt=fmt, actor_id=None, owner_id=None)
            elapsed = time.perf_counter() - start
    finally:
        await engine.dispose()

    target = 30.0  # NFR-PRF-05: 30 секунд
    return Scenario3Result(
        sessions=session_count,
        format=fmt.value,
        wall_time_s=elapsed,
        target_s=target,
        passed=elapsed <= target,
        file_size=report.file_size,
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="NFR-PRF-05 report generation")
    parser.add_argument("--sessions", type=int, default=500)
    parser.add_argument("--format", choices=["pdf", "xlsx"], default="pdf")
    args = parser.parse_args()

    fmt = ReportFormat.PDF if args.format == "pdf" else ReportFormat.XLSX
    result = run(_seed_and_generate(args.sessions, fmt))
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
