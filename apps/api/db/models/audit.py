"""Журнал аудита (FR-DB-05, FR-AUTH-07)."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from apps.api.db.base import Base

# Кросс-диалектные типы: на Postgres — INET / JSONB, на SQLite (только для тестов)
# fallback на String / JSON, чтобы create_all не падал.
_INET = INET().with_variant(String(45), "sqlite")
_JSONB = JSONB().with_variant(JSON(), "sqlite")


class AuditAction(str, enum.Enum):
    """Перечень аудируемых действий, установленный спецификацией."""

    USER_CREATED = "user_created"
    USER_EDITED = "user_edited"
    USER_DEACTIVATED = "user_deactivated"
    PASSWORD_RESET = "password_reset"
    ROLE_ASSIGNED = "role_assigned"
    LOGIN_SUCCESSFUL = "login_successful"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    ML_CONFIG_CHANGED = "ml_config_changed"
    DATA_DELETION_REQUESTED = "data_deletion_requested"


class AuditLog(Base):
    """Запись журнала аудита. Не содержит updated_at — записи иммутабельны."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_performed_user", "performed_at", "user_id"),
        Index("ix_audit_log_action", "action"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action", create_constraint=True),
        nullable=False,
    )
    performed_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    campaign_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(_INET, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(_JSONB, nullable=True)
