"""add reports table for generated PDF/XLSX metadata (FR-RPT-08)

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-09 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REPORT_FORMAT_VALUES = ("pdf", "xlsx")


def upgrade() -> None:
    report_format = postgresql.ENUM(
        *REPORT_FORMAT_VALUES, name="report_format", create_type=False
    )
    bind = op.get_bind()
    report_format.create(bind, checkfirst=True)

    op.create_table(
        "reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "campaign_id",
            sa.BigInteger(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "format",
            postgresql.ENUM(name="report_format", create_type=False),
            nullable=False,
        ),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.LargeBinary(32), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "generated_by_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("file_size > 0", name="ck_reports_file_size_positive"),
    )
    op.create_index("ix_reports_campaign_format", "reports", ["campaign_id", "format"])
    op.create_index("ix_reports_generated_at", "reports", ["generated_at"])


def downgrade() -> None:
    op.drop_index("ix_reports_generated_at", table_name="reports")
    op.drop_index("ix_reports_campaign_format", table_name="reports")
    op.drop_table("reports")

    bind = op.get_bind()
    sa.Enum(name="report_format").drop(bind, checkfirst=True)
