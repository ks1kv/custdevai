"""Административные операции, не связанные с пользовательскими сущностями.

FR-DB-07: безвозвратное удаление данных субъекта (№ 152-ФЗ). Эндпоинт
доступен только Admin-роли; для самостоятельного удаления субъектом
через бота — отдельный механизм (Phase 6: deep-link с одноразовым
токеном, выходит за scope MUST Phase 5).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from apps.api.auth.rbac import Role
from apps.api.deps import (
    CurrentUser,
    DBSession,
    get_client_ip,
    require_roles,
)
from apps.api.services.data_deletion import DataDeletionService

router = APIRouter(prefix="/admin", tags=["admin"])


class DataDeletionRequest(BaseModel):
    """Запрос на удаление по hex-представлению SHA-256 хеша."""

    telegram_id_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")


class DataDeletionResponse(BaseModel):
    performed_at: str
    telegram_id_hash: str
    affected: dict[str, int]
    audit_id: int | None
    legal_basis: str = "ФЗ-152 ст. 14 ч. 1 (право субъекта на удаление)"


@router.post(
    "/data-deletion-requests",
    status_code=status.HTTP_200_OK,
    response_model=DataDeletionResponse,
    summary="Безвозвратно удалить данные субъекта по telegram_id_hash (FR-DB-07)",
)
async def request_data_deletion(
    payload: DataDeletionRequest,
    request: Request,
    session: DBSession,
    actor: CurrentUser = Depends(require_roles(Role.ADMIN)),
) -> DataDeletionResponse:
    """Удаление всех записей субъекта по его SHA-256 хешу.

    Удаление физическое и невосстановимое. В audit_log пишется запись
    DATA_DELETION_REQUESTED с counts и legal_basis. Сам telegram_id_hash
    не сохраняется в audit-deatils (только в response для клиента).
    """
    service = DataDeletionService(session)
    receipt = await service.delete_by_telegram_hash(
        bytes.fromhex(payload.telegram_id_hash),
        actor_user_id=actor.id,
        ip_address=get_client_ip(request),
    )
    return DataDeletionResponse(
        performed_at=receipt.performed_at.isoformat(),
        telegram_id_hash=receipt.telegram_id_hash_hex,
        affected=receipt.affected,
        audit_id=receipt.audit_id,
    )
