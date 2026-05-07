"""add campaign analysis fields and ENUM

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-08 00:00:00.000000

Расширяет таблицу campaigns полями для оркестрации ML-пайплайна
(FR-API-04, FR-TOP-04, FR-RPT-07):

  - ENUM campaign_analysis_status: pending|running|completed|failed
  - analysis_status (default 'pending', индексируется)
  - target_topic_count (default 10, CHECK BETWEEN 3 AND 20)
  - analysis_started_at / analysis_completed_at / analysis_error
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ANALYSIS_STATUS_VALUES = ("pending", "running", "completed", "failed")


def upgrade() -> None:
    analysis_status = postgresql.ENUM(
        *ANALYSIS_STATUS_VALUES,
        name="campaign_analysis_status",
        create_type=False,
    )
    bind = op.get_bind()
    analysis_status.create(bind, checkfirst=True)

    op.add_column(
        "campaigns",
        sa.Column(
            "analysis_status",
            postgresql.ENUM(name="campaign_analysis_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column(
            "target_topic_count",
            sa.SmallInteger(),
            nullable=False,
            server_default="10",
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column("analysis_started_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        "campaigns",
        sa.Column(
            "analysis_completed_at", sa.DateTime(timezone=False), nullable=True
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column("analysis_error", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_campaigns_target_topic_count_range",
        "campaigns",
        "target_topic_count BETWEEN 3 AND 20",
    )
    op.create_index(
        "ix_campaigns_analysis_status", "campaigns", ["analysis_status"]
    )


def downgrade() -> None:
    op.drop_index("ix_campaigns_analysis_status", table_name="campaigns")
    op.drop_constraint(
        "ck_campaigns_target_topic_count_range", "campaigns", type_="check"
    )
    op.drop_column("campaigns", "analysis_error")
    op.drop_column("campaigns", "analysis_completed_at")
    op.drop_column("campaigns", "analysis_started_at")
    op.drop_column("campaigns", "target_topic_count")
    op.drop_column("campaigns", "analysis_status")

    bind = op.get_bind()
    sa.Enum(name="campaign_analysis_status").drop(bind, checkfirst=True)
