"""Модель Report — метаданные сгенерированного PDF/XLSX (FR-RPT-08)."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.db.base import Base, TimestampMixin


class ReportFormat(str, enum.Enum):
    """Формат сгенерированного отчёта (FR-RPT-02, FR-RPT-03)."""

    PDF = "pdf"
    XLSX = "xlsx"


class Report(Base, TimestampMixin):
    """Запись о сгенерированном отчёте.

    Файл хранится в `StorageBackend` (Phase 4 — LocalFileSystemBackend,
    Phase 5 — S3StorageBackend). `file_path` — абстрактный ключ, понятный
    конкретному backend-у. `sha256` — SHA-256 хеш контента для
    integrity-check (FR-RPT-08).

    ON DELETE CASCADE на campaign_id: удаление кампании удаляет все
    связанные записи (FR-RPT-08 «срок существования соответствующей
    кампании»). Файлы из storage чистит sweeper Phase 5.

    Уникальность пары (campaign_id, format) НЕ ставим — повторная
    генерация по запросу (FR-RPT-07) создаёт новую запись.
    """

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("file_size > 0", name="ck_reports_file_size_positive"),
        Index("ix_reports_campaign_format", "campaign_id", "format"),
        Index("ix_reports_generated_at", "generated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    format: Mapped[ReportFormat] = mapped_column(
        Enum(
            ReportFormat,
            name="report_format",
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        nullable=False,
    )
    generated_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
