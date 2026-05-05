"""DTO для кампаний."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from apps.api.db.models import CampaignStatus


class CampaignCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    script_id: int = Field(gt=0)


class CampaignUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    status: CampaignStatus | None = None


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    script_id: int
    created_by_user_id: int | None
    status: CampaignStatus
    invitation_url: str | None
    started_at: datetime | None
    completed_at: datetime | None
    has_pseudonym_salt: bool = False

    @classmethod
    def from_orm_with_flag(cls, campaign: object) -> CampaignOut:
        out = cls.model_validate(campaign)
        out.has_pseudonym_salt = bool(getattr(campaign, "pseudonym_salt", None))
        return out
