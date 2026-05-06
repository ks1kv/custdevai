"""add consents table and users.researcher_telegram_chat_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-06 00:00:00.000000

Создаёт таблицу consents (FR-BOT-01, явное согласие на обработку
данных по № 152-ФЗ) и добавляет колонку
users.researcher_telegram_chat_id для push-уведомлений (FR-BOT-09).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ip_address_hash", sa.LargeBinary(32), nullable=True),
        sa.Column("consent_version", sa.String(32), nullable=False),
    )
    op.create_index("ix_consents_granted_at", "consents", ["granted_at"])

    op.add_column(
        "users",
        sa.Column("researcher_telegram_chat_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "researcher_telegram_chat_id")
    op.drop_index("ix_consents_granted_at", table_name="consents")
    op.drop_table("consents")
