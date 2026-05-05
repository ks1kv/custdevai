"""initial schema with 12 tables, ENUM-types and role seed

Revision ID: 0001
Revises:
Create Date: 2026-05-05 00:00:00.000000

Создаёт всю Phase 1-схему одной ревизией: 12 таблиц нормализованных до 3NF,
4 native PostgreSQL ENUM-а, B-Tree индексы под FR-DB-04, заполняет таблицу
ролей четырьмя предопределёнными значениями RBAC.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CAMPAIGN_STATUS_VALUES = ("draft", "running", "paused", "completed")
SESSION_STATUS_VALUES = ("active", "completed", "interrupted")
SENTIMENT_LABEL_VALUES = ("positive", "neutral", "negative", "low_confidence")
AUDIT_ACTION_VALUES = (
    "user_created",
    "user_edited",
    "user_deactivated",
    "password_reset",
    "role_assigned",
    "login_successful",
    "login_failed",
    "logout",
    "ml_config_changed",
    "data_deletion_requested",
)


def upgrade() -> None:
    # ENUM types -----------------------------------------------------------
    campaign_status = postgresql.ENUM(
        *CAMPAIGN_STATUS_VALUES, name="campaign_status", create_type=False
    )
    session_status = postgresql.ENUM(
        *SESSION_STATUS_VALUES, name="session_status", create_type=False
    )
    sentiment_label = postgresql.ENUM(
        *SENTIMENT_LABEL_VALUES, name="sentiment_label", create_type=False
    )
    audit_action = postgresql.ENUM(
        *AUDIT_ACTION_VALUES, name="audit_action", create_type=False
    )
    bind = op.get_bind()
    campaign_status.create(bind, checkfirst=True)
    session_status.create(bind, checkfirst=True)
    sentiment_label.create(bind, checkfirst=True)
    audit_action.create(bind, checkfirst=True)

    # users ----------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(60), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "failed_login_count",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("locked_until", sa.DateTime(timezone=False), nullable=True),
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
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_is_active", "users", ["is_active"])

    # roles ----------------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(32), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
    )

    # user_roles (M:N) -----------------------------------------------------
    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            sa.SmallInteger(),
            sa.ForeignKey("roles.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    # scripts --------------------------------------------------------------
    op.create_table(
        "scripts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
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
    )
    op.create_index(
        "ix_scripts_created_by_user_id", "scripts", ["created_by_user_id"]
    )

    # questions ------------------------------------------------------------
    op.create_table(
        "questions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "script_id",
            sa.BigInteger(),
            sa.ForeignKey("scripts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_index", sa.SmallInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "is_required", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("hint_text", sa.Text(), nullable=True),
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
        sa.UniqueConstraint(
            "script_id", "order_index", name="uq_questions_script_order"
        ),
    )
    op.create_index("ix_questions_script_id", "questions", ["script_id"])

    # campaigns ------------------------------------------------------------
    op.create_table(
        "campaigns",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "script_id",
            sa.BigInteger(),
            sa.ForeignKey("scripts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="campaign_status", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("pseudonym_salt", sa.LargeBinary(32), nullable=False),
        sa.Column("invitation_url", sa.String(512), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=False), nullable=True),
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
    )
    op.create_index("ix_campaigns_status", "campaigns", ["status"])
    op.create_index("ix_campaigns_script_id", "campaigns", ["script_id"])
    op.create_index(
        "ix_campaigns_created_by_user_id", "campaigns", ["created_by_user_id"]
    )
    op.create_index(
        "ix_campaigns_status_created_at", "campaigns", ["status", "created_at"]
    )

    # sessions -------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "campaign_id",
            sa.BigInteger(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_id_hash", sa.LargeBinary(32), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="session_status", create_type=False),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "progress_count", sa.SmallInteger(), nullable=False, server_default="0"
        ),
        sa.Column("started_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=False), nullable=True),
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
        sa.UniqueConstraint(
            "campaign_id", "telegram_id_hash", name="uq_sessions_campaign_telegram"
        ),
    )
    op.create_index(
        "ix_sessions_campaign_status", "sessions", ["campaign_id", "status"]
    )
    op.create_index(
        "ix_sessions_campaign_started", "sessions", ["campaign_id", "started_at"]
    )
    op.create_index("ix_sessions_last_activity", "sessions", ["last_activity_at"])

    # answers --------------------------------------------------------------
    op.create_table(
        "answers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.BigInteger(),
            sa.ForeignKey("questions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=False), nullable=False),
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
        sa.UniqueConstraint(
            "session_id", "question_id", name="uq_answers_session_question"
        ),
        sa.CheckConstraint(
            "char_length(text) BETWEEN 1 AND 4096",
            name="answers_text_length",
        ),
    )
    op.create_index("ix_answers_session_id", "answers", ["session_id"])

    # topics ---------------------------------------------------------------
    op.create_table(
        "topics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "campaign_id",
            sa.BigInteger(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("topic_id_in_model", sa.SmallInteger(), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "frequency_count", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "is_noise", sa.Boolean(), nullable=False, server_default=sa.false()
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
    )
    op.create_index("ix_topics_campaign_id", "topics", ["campaign_id"])

    # session_topics (M:N) -------------------------------------------------
    op.create_table(
        "session_topics",
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "topic_id",
            sa.BigInteger(),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("representative_quote", sa.Text(), nullable=True),
    )
    op.create_index("ix_session_topics_topic_id", "session_topics", ["topic_id"])

    # sentiment_results ----------------------------------------------------
    op.create_table(
        "sentiment_results",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "answer_id",
            sa.BigInteger(),
            sa.ForeignKey("answers.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "label",
            postgresql.ENUM(name="sentiment_label", create_type=False),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=False), nullable=False),
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
    )
    op.create_index(
        "ix_sentiment_answer_label", "sentiment_results", ["answer_id", "label"]
    )

    # audit_log ------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "action",
            postgresql.ENUM(name="audit_action", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "performed_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "target_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "campaign_id",
            sa.BigInteger(),
            sa.ForeignKey("campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_audit_log_performed_user", "audit_log", ["performed_at", "user_id"]
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"])

    # Seed roles -----------------------------------------------------------
    op.bulk_insert(
        sa.table(
            "roles",
            sa.column("id", sa.SmallInteger()),
            sa.column("name", sa.String()),
            sa.column("description", sa.String()),
        ),
        [
            {"id": 1, "name": "Admin", "description": "Администратор системы"},
            {"id": 2, "name": "Researcher", "description": "Исследователь — автор сценариев и кампаний"},
            {"id": 3, "name": "Analyst", "description": "Аналитик данных — просмотр результатов"},
            {"id": 4, "name": "Respondent", "description": "Респондент Telegram-бота"},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_performed_user", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_sentiment_answer_label", table_name="sentiment_results")
    op.drop_table("sentiment_results")

    op.drop_index("ix_session_topics_topic_id", table_name="session_topics")
    op.drop_table("session_topics")

    op.drop_index("ix_topics_campaign_id", table_name="topics")
    op.drop_table("topics")

    op.drop_index("ix_answers_session_id", table_name="answers")
    op.drop_table("answers")

    op.drop_index("ix_sessions_last_activity", table_name="sessions")
    op.drop_index("ix_sessions_campaign_started", table_name="sessions")
    op.drop_index("ix_sessions_campaign_status", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_campaigns_status_created_at", table_name="campaigns")
    op.drop_index("ix_campaigns_created_by_user_id", table_name="campaigns")
    op.drop_index("ix_campaigns_script_id", table_name="campaigns")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_table("campaigns")

    op.drop_index("ix_questions_script_id", table_name="questions")
    op.drop_table("questions")

    op.drop_index("ix_scripts_created_by_user_id", table_name="scripts")
    op.drop_table("scripts")

    op.drop_index("ix_user_roles_role_id", table_name="user_roles")
    op.drop_table("user_roles")

    op.drop_table("roles")

    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_name in ("audit_action", "sentiment_label", "session_status", "campaign_status"):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
