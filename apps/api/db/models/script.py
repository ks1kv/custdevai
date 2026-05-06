"""Модели Script (сценарий интервью) и Question."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.db.base import Base, TimestampMixin


class Script(Base, TimestampMixin):
    """Сценарий интервью — корневая сущность, на которую ссылаются кампании."""

    __tablename__ = "scripts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    questions: Mapped[list[Question]] = relationship(
        back_populates="script",
        cascade="all, delete-orphan",
        order_by="Question.order_index",
        lazy="selectin",
    )


class Question(Base, TimestampMixin):
    """Вопрос внутри сценария. Удаляется каскадно при удалении сценария."""

    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("script_id", "order_index", name="uq_questions_script_order"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hint_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    script: Mapped[Script] = relationship(back_populates="questions")
