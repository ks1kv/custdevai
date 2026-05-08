"""Reports REST API: генерация, список, скачивание (FR-RPT-01..08, FR-WEB-10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from apps.api.auth.rbac import Role
from apps.api.db.models import ReportFormat
from apps.api.deps import CurrentUser, DBSession, SettingsDep, require_roles
from apps.api.reports.service import ReportService
from apps.api.schemas.pagination import Page, PaginationParams, pagination_dependency
from apps.api.schemas.report import ReportOut

router = APIRouter(prefix="/campaigns/{campaign_id}/reports", tags=["reports"])

_writer = require_roles(Role.RESEARCHER, Role.ADMIN)
_reader = require_roles(Role.RESEARCHER, Role.ANALYST, Role.ADMIN)


def _owner_filter(actor: CurrentUser) -> int | None:
    """Researcher видит только свои; Analyst и Admin — все."""
    if Role.ADMIN.value in actor.roles or Role.ANALYST.value in actor.roles:
        return None
    return actor.id


@router.post(
    "/generate",
    response_model=ReportOut,
    summary="Сгенерировать PDF/XLSX отчёт по кампании (FR-RPT-01..05)",
)
async def generate_report(
    campaign_id: int,
    session: DBSession,
    settings: SettingsDep,
    fmt: ReportFormat = Query(ReportFormat.PDF, alias="format"),
    actor: CurrentUser = Depends(_writer),
) -> ReportOut:
    service = ReportService(session=session, settings=settings)
    report = await service.generate(
        campaign_id,
        fmt=fmt,
        actor_id=actor.id,
        owner_id=_owner_filter(actor),
    )
    return ReportOut.model_validate(report)


@router.get(
    "",
    response_model=Page[ReportOut],
    summary="Список отчётов кампании",
)
async def list_reports(
    campaign_id: int,
    session: DBSession,
    settings: SettingsDep,
    pagination: PaginationParams = Depends(pagination_dependency),
    actor: CurrentUser = Depends(_reader),
) -> Page[ReportOut]:
    pagination.validated()
    from apps.api.db.repositories.reports import ReportRepository

    # Доступ — через ReportService.get() было бы тяжело для list-а;
    # вместо этого проверяем владение кампанией один раз.
    service = ReportService(session=session, settings=settings)
    # Минимальный gate: загружаем кампанию через сервис, кидаем NotFound
    # если её нет / не принадлежит. Используем report-repo напрямую для list.
    from apps.api.db.repositories.campaigns import CampaignRepository

    owner_id = _owner_filter(actor)
    campaign = await CampaignRepository(session).get(campaign_id)
    if campaign is None or (owner_id is not None and campaign.created_by_user_id != owner_id):
        from apps.api.errors import NotFound

        raise NotFound("Кампания не найдена.")

    items, total = await ReportRepository(session).list_for_campaign(
        campaign_id, limit=pagination.limit, offset=pagination.offset
    )
    return Page[ReportOut](
        items=[ReportOut.model_validate(r) for r in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/{report_id}/download",
    summary="Скачать сгенерированный отчёт",
)
async def download_report(
    campaign_id: int,
    report_id: int,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_reader),
) -> Response:
    service = ReportService(session=session, settings=settings)
    report = await service.get(report_id, owner_id=_owner_filter(actor))
    if report.campaign_id != campaign_id:
        from apps.api.errors import NotFound

        raise NotFound("Отчёт не найден в указанной кампании.")
    data = await service.read_bytes(report)

    filename = f"campaign-{report.campaign_id}-{report.id}.{report.format.value}"
    media_type = (
        "application/pdf"
        if report.format == ReportFormat.PDF
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(data)),
        },
    )
