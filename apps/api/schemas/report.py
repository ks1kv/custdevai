"""DTO для отчётов."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from apps.api.db.models import ReportFormat


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    format: ReportFormat
    file_size: int
    generated_at: datetime
    generated_by_user_id: int | None
