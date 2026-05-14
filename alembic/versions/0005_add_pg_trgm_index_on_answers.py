"""add GIN trigram index on answers.text for full-text search (FR-WEB-05)

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-14 00:00:00.000000

pg_trgm-расширение уже включается в scripts/db/init/00_extensions.sql.
Phase 5: добавляем GIN-индекс на `answers.text` для поддержки
полнотекстового поиска по транскриптам через `text % :q` или
`text ILIKE :q` (FR-WEB-05).

Индекс CONCURRENTLY НЕ используется — на этапе alembic upgrade БД ещё
не имеет нагрузки. В production restore операция тоже происходит на
свободной БД.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # На случай восстановления на чистом инстансе — гарантируем расширение.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_answers_text_trgm "
        "ON answers USING gin (text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_answers_text_trgm")
