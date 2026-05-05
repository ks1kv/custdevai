"""CRUD сценариев интервью (FR-API-01, FR-API-06, NFR-PRF-03)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from apps.api.auth.rbac import Role
from apps.api.deps import CurrentUser, DBSession, get_current_user, require_roles
from apps.api.schemas.pagination import Page, PaginationParams
from apps.api.schemas.script import (
    QuestionIn,
    QuestionOut,
    QuestionUpsert,
    ScriptCreate,
    ScriptOut,
    ScriptUpdate,
)
from apps.api.services.scripts import ScriptService

router = APIRouter(prefix="/scripts", tags=["scripts"])

_writer = require_roles(Role.RESEARCHER, Role.ADMIN)
_reader = require_roles(Role.RESEARCHER, Role.ANALYST, Role.ADMIN)


def _owner_filter(actor: CurrentUser) -> int | None:
    """Researcher видит только свои сценарии. Analyst и Admin — все."""
    if Role.ADMIN.value in actor.roles or Role.ANALYST.value in actor.roles:
        return None
    return actor.id


def _to_out(script: object) -> ScriptOut:
    return ScriptOut.model_validate(script)


@router.get("", response_model=Page[ScriptOut], summary="Список сценариев")
async def list_scripts(
    session: DBSession,
    pagination: PaginationParams = Depends(PaginationParams),
    actor: CurrentUser = Depends(_reader),
) -> Page[ScriptOut]:
    pagination.validated()
    service = ScriptService(session)
    items, total = await service.list_(
        limit=pagination.limit,
        offset=pagination.offset,
        owner_id=_owner_filter(actor),
    )
    return Page[ScriptOut](
        items=[_to_out(s) for s in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post("", response_model=ScriptOut, summary="Создать сценарий")
async def create_script(
    payload: ScriptCreate,
    session: DBSession,
    actor: CurrentUser = Depends(_writer),
) -> ScriptOut:
    service = ScriptService(session)
    script = await service.create(payload, owner_id=actor.id)
    return _to_out(script)


@router.get("/{script_id}", response_model=ScriptOut, summary="Получить сценарий")
async def get_script(
    script_id: int,
    session: DBSession,
    actor: CurrentUser = Depends(_reader),
) -> ScriptOut:
    service = ScriptService(session)
    return _to_out(await service.get(script_id, owner_id=_owner_filter(actor)))


@router.patch("/{script_id}", response_model=ScriptOut, summary="Обновить сценарий")
async def update_script(
    script_id: int,
    payload: ScriptUpdate,
    session: DBSession,
    actor: CurrentUser = Depends(_writer),
) -> ScriptOut:
    service = ScriptService(session)
    return _to_out(await service.update(script_id, payload, owner_id=_owner_filter(actor)))


@router.delete(
    "/{script_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Удалить сценарий (409 при наличии любых кампаний)",
)
async def delete_script(
    script_id: int,
    session: DBSession,
    actor: CurrentUser = Depends(_writer),
) -> Response:
    service = ScriptService(session)
    await service.delete(script_id, owner_id=_owner_filter(actor))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{script_id}/questions",
    response_model=QuestionOut,
    summary="Добавить вопрос в сценарий",
)
async def add_question(
    script_id: int,
    payload: QuestionIn,
    session: DBSession,
    actor: CurrentUser = Depends(_writer),
) -> QuestionOut:
    service = ScriptService(session)
    q = await service.add_question(script_id, payload, owner_id=_owner_filter(actor))
    return QuestionOut.model_validate(q)


@router.patch(
    "/{script_id}/questions/{question_id}",
    response_model=QuestionOut,
    summary="Обновить вопрос",
)
async def update_question(
    script_id: int,
    question_id: int,
    payload: QuestionUpsert,
    session: DBSession,
    actor: CurrentUser = Depends(_writer),
) -> QuestionOut:
    service = ScriptService(session)
    q = await service.update_question(
        script_id, question_id, payload, owner_id=_owner_filter(actor)
    )
    return QuestionOut.model_validate(q)


@router.delete(
    "/{script_id}/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Удалить вопрос",
)
async def delete_question(
    script_id: int,
    question_id: int,
    session: DBSession,
    actor: CurrentUser = Depends(_writer),
) -> Response:
    service = ScriptService(session)
    await service.delete_question(script_id, question_id, owner_id=_owner_filter(actor))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ensure dependency is referenced for static analysis
_ = get_current_user
