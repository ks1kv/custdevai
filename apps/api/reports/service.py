"""ReportService — оркестрация генерации и хранения отчётов."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import Settings
from apps.api.db.models import (
    Campaign,
    CampaignAnalysisStatus,
    Report,
    ReportFormat,
)
from apps.api.db.repositories.campaigns import CampaignRepository
from apps.api.db.repositories.reports import ReportRepository
from apps.api.errors import Conflict, NotFound
from apps.api.reports.data_loader import (
    CampaignReportContext,
    load_campaign_report_context,
)
from apps.api.reports.generators.pdf import PDFReportGenerator
from apps.api.reports.generators.xlsx import XLSXReportGenerator
from apps.api.reports.storage import StorageBackend, get_storage_backend

logger = logging.getLogger(__name__)


def _utcnaive(dt: datetime | None = None) -> datetime:
    return (dt or datetime.now(tz=timezone.utc)).replace(tzinfo=None)


class ReportService:
    """Генерация и сохранение PDF/XLSX отчётов кампании.

    Вызывается из роутера. CPU-bound рендер выносится в
    `loop.run_in_executor`, чтобы не блокировать event loop FastAPI.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        storage: StorageBackend | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._storage = storage or get_storage_backend(settings)
        self._campaigns = CampaignRepository(session)
        self._reports = ReportRepository(session)

    async def generate(
        self,
        campaign_id: int,
        *,
        fmt: ReportFormat,
        actor_id: int | None,
        owner_id: int | None,
    ) -> Report:
        """Сгенерировать и сохранить отчёт.

        FR-RPT-06: целевой бюджет ≤ 30 секунд для 500 сессий. Мы запускаем
        ReportLab/openpyxl в threadpool, чтобы не блокировать другие запросы.

        FR-RPT-07: повторная генерация поддерживается (создаётся новая
        запись reports — старая не удаляется, файл остаётся в storage до
        cleanup-задачи Phase 5).
        """
        campaign = await self._campaigns.get(campaign_id)
        if campaign is None:
            raise NotFound("Кампания не найдена.")
        if owner_id is not None and campaign.created_by_user_id != owner_id:
            raise NotFound("Кампания не найдена.")
        if campaign.analysis_status != CampaignAnalysisStatus.COMPLETED:
            raise Conflict(
                "ML-анализ кампании ещё не завершён. Запустите анализ "
                "и дождитесь статуса completed перед генерацией отчёта."
            )

        now = _utcnaive()
        ctx = await load_campaign_report_context(
            self._session, campaign_id, generated_at=now
        )

        # CPU-bound рендер в threadpool.
        loop = asyncio.get_event_loop()
        if fmt == ReportFormat.PDF:
            data = await loop.run_in_executor(None, _render_pdf_sync, ctx)
            extension = "pdf"
            content_type = "application/pdf"
        elif fmt == ReportFormat.XLSX:
            data = await loop.run_in_executor(None, _render_xlsx_sync, ctx)
            extension = "xlsx"
            content_type = (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        else:  # pragma: no cover  — ENUM защищает
            raise ValueError(f"Unsupported format: {fmt}")

        # Ключ уникальный по дате, чтобы re-run не перезаписывал старый файл.
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        key = f"campaigns/{campaign_id}/{timestamp}-report.{extension}"
        put_result = await self._storage.put(key, data, content_type=content_type)

        report = Report(
            campaign_id=campaign_id,
            format=fmt,
            file_path=put_result.file_path,
            file_size=put_result.file_size,
            sha256=put_result.sha256,
            generated_at=now,
            generated_by_user_id=actor_id,
        )
        await self._reports.add(report)
        await self._session.commit()
        await self._session.refresh(report)

        logger.info(
            "report_generated",
            extra={
                "report_id": report.id,
                "campaign_id": campaign_id,
                "format": fmt.value,
                "size": put_result.file_size,
                "actor_id": actor_id,
            },
        )
        return report

    async def get(self, report_id: int, *, owner_id: int | None) -> Report:
        report = await self._reports.get(report_id)
        if report is None:
            raise NotFound("Отчёт не найден.")
        # Защищаем доступ через campaign-ownership.
        campaign = await self._campaigns.get(report.campaign_id)
        if campaign is None:
            raise NotFound("Отчёт не найден.")
        if owner_id is not None and campaign.created_by_user_id != owner_id:
            raise NotFound("Отчёт не найден.")
        return report

    async def read_bytes(self, report: Report) -> bytes:
        obj = await self._storage.get(report.file_path)
        return obj.content


def _render_pdf_sync(ctx: CampaignReportContext) -> bytes:
    return PDFReportGenerator(ctx).render()


def _render_xlsx_sync(ctx: CampaignReportContext) -> bytes:
    return XLSXReportGenerator(ctx).render()
