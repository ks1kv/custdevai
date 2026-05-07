"""Реэкспорт всех ORM-моделей.

Этот модуль импортируется alembic/env.py, чтобы зарегистрировать каждую
модель в `Base.metadata` и autogenerate видел все таблицы.
"""

from apps.api.db.base import Base
from apps.api.db.models.analysis import (
    SentimentLabel,
    SentimentResult,
    SessionTopic,
    Topic,
)
from apps.api.db.models.audit import AuditAction, AuditLog
from apps.api.db.models.campaign import Campaign, CampaignAnalysisStatus, CampaignStatus
from apps.api.db.models.consent import Consent
from apps.api.db.models.script import Question, Script
from apps.api.db.models.session import Answer, InterviewSession, SessionStatus
from apps.api.db.models.user import Role, User, UserRole

__all__ = [
    "Answer",
    "AuditAction",
    "AuditLog",
    "Base",
    "Campaign",
    "CampaignAnalysisStatus",
    "CampaignStatus",
    "Consent",
    "InterviewSession",
    "Question",
    "Role",
    "Script",
    "SentimentLabel",
    "SentimentResult",
    "SessionStatus",
    "SessionTopic",
    "Topic",
    "User",
    "UserRole",
]
