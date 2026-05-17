"""DTO для кампаний."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from apps.api.db.models import CampaignAnalysisStatus, CampaignStatus


class CampaignCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    script_id: int = Field(gt=0)
    target_topic_count: int = Field(default=10, ge=3, le=20)


class CampaignUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    status: CampaignStatus | None = None
    target_topic_count: int | None = Field(default=None, ge=3, le=20)


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
    analysis_status: CampaignAnalysisStatus = CampaignAnalysisStatus.PENDING
    target_topic_count: int = 10

    @classmethod
    def from_orm_with_flag(cls, campaign: object) -> CampaignOut:
        out = cls.model_validate(campaign)
        out.has_pseudonym_salt = bool(getattr(campaign, "pseudonym_salt", None))
        return out


class CampaignAnalysisStatusOut(BaseModel):
    campaign_id: int
    analysis_status: CampaignAnalysisStatus
    analysis_started_at: datetime | None
    analysis_completed_at: datetime | None
    analysis_error: str | None
    target_topic_count: int


class CampaignAnalysisQueued(BaseModel):
    campaign_id: int
    task_id: str
    status: str = "queued"


class TopicSummaryItem(BaseModel):
    label: str | None
    keywords: list[str]
    frequency_count: int


class CampaignSummaryOut(BaseModel):
    """Лёгкая сводка по кампании для side-by-side сравнения (FR-WEB-08).

    Возвращает только агрегации: распределение тональности, топ-темы,
    счётчики сессий — без транскриптов и цитат. Отдельный endpoint от
    /reports, чтобы не тянуть тяжёлый DataLoader на каждое сравнение.
    """

    campaign_id: int
    title: str
    description: str | None
    status: CampaignStatus
    analysis_status: CampaignAnalysisStatus
    target_topic_count: int
    sessions_total: int
    sessions_completed: int
    answers_total: int
    sentiment_distribution: dict[str, int]
    topics_top: list[TopicSummaryItem]
