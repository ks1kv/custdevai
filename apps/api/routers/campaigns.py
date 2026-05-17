"""CRUD кампаний (FR-API-01, FR-API-06, FR-DB-03, NFR-PRF-03)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from apps.api.auth.rbac import Role
from apps.api.db.models import CampaignStatus
from apps.api.deps import CurrentUser, DBSession, SettingsDep, require_roles
from apps.api.schemas.campaign import (
    CampaignAnalysisQueued,
    CampaignAnalysisStatusOut,
    CampaignCreate,
    CampaignOut,
    CampaignSummaryOut,
    CampaignUpdate,
)
from apps.api.schemas.pagination import Page, PaginationParams, pagination_dependency
from apps.api.services.campaigns import CampaignService

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

_writer = require_roles(Role.RESEARCHER, Role.ADMIN)
_reader = require_roles(Role.RESEARCHER, Role.ANALYST, Role.ADMIN)


def _owner_filter(actor: CurrentUser) -> int | None:
    if Role.ADMIN.value in actor.roles or Role.ANALYST.value in actor.roles:
        return None
    return actor.id


@router.get("", response_model=Page[CampaignOut], summary="Список кампаний")
async def list_campaigns(
    session: DBSession,
    settings: SettingsDep,
    pagination: PaginationParams = Depends(pagination_dependency),
    status_filter: CampaignStatus | None = None,
    actor: CurrentUser = Depends(_reader),
) -> Page[CampaignOut]:
    pagination.validated()
    service = CampaignService(session, settings)
    items, total = await service.list_(
        limit=pagination.limit,
        offset=pagination.offset,
        owner_id=_owner_filter(actor),
        status_filter=status_filter,
    )
    return Page[CampaignOut](
        items=[CampaignOut.from_orm_with_flag(c) for c in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post("", response_model=CampaignOut, summary="Создать кампанию")
async def create_campaign(
    payload: CampaignCreate,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_writer),
) -> CampaignOut:
    service = CampaignService(session, settings)
    campaign = await service.create(payload, owner_id=actor.id)
    return CampaignOut.from_orm_with_flag(campaign)


@router.get("/{campaign_id}", response_model=CampaignOut, summary="Получить кампанию")
async def get_campaign(
    campaign_id: int,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_reader),
) -> CampaignOut:
    service = CampaignService(session, settings)
    campaign = await service.get(campaign_id, owner_id=_owner_filter(actor))
    return CampaignOut.from_orm_with_flag(campaign)


@router.patch("/{campaign_id}", response_model=CampaignOut, summary="Обновить кампанию")
async def update_campaign(
    campaign_id: int,
    payload: CampaignUpdate,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_writer),
) -> CampaignOut:
    service = CampaignService(session, settings)
    campaign = await service.update(campaign_id, payload, owner_id=_owner_filter(actor))
    return CampaignOut.from_orm_with_flag(campaign)


@router.delete(
    "/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Удалить кампанию",
)
async def delete_campaign(
    campaign_id: int,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_writer),
) -> Response:
    service = CampaignService(session, settings)
    await service.delete(campaign_id, owner_id=_owner_filter(actor))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{campaign_id}/analyze",
    response_model=CampaignAnalysisQueued,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запустить ML-анализ кампании (FR-API-04, FR-RPT-07)",
)
async def analyze_campaign_endpoint(
    campaign_id: int,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_writer),
) -> CampaignAnalysisQueued:
    service = CampaignService(session, settings)
    task_id = await service.enqueue_analysis(campaign_id, owner_id=_owner_filter(actor))
    return CampaignAnalysisQueued(campaign_id=campaign_id, task_id=task_id)


@router.get(
    "/{campaign_id}/analysis-status",
    response_model=CampaignAnalysisStatusOut,
    summary="Получить статус ML-пайплайна кампании",
)
async def get_analysis_status_endpoint(
    campaign_id: int,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_reader),
) -> CampaignAnalysisStatusOut:
    service = CampaignService(session, settings)
    data = await service.get_analysis_status(campaign_id, owner_id=_owner_filter(actor))
    return CampaignAnalysisStatusOut.model_validate(data)


@router.get(
    "/{campaign_id}/summary",
    response_model=CampaignSummaryOut,
    summary="Лёгкая сводка кампании для сравнения (FR-WEB-08)",
)
async def get_campaign_summary(
    campaign_id: int,
    session: DBSession,
    settings: SettingsDep,
    actor: CurrentUser = Depends(_reader),
) -> CampaignSummaryOut:
    service = CampaignService(session, settings)
    data = await service.get_summary(campaign_id, owner_id=_owner_filter(actor))
    return CampaignSummaryOut.model_validate(data)
